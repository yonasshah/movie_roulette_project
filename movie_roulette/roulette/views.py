# movie_roulette/roulette/views.py

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404, JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.conf import settings
import requests
from django.utils.safestring import mark_safe # Import mark_safe
from django.utils.html import escape # Import escape
from django.contrib.contenttypes.models import ContentType
from .forms import ShareListForm, UserListForm, ReviewForm, CommentForm # Add CommentForm
from .models import Notification, SharedListPost, UserContent, UserFollow, UserList, UserReview, Comment, Like, SharedListPost, Vote # Add Comment, Like
import random
from django.contrib.auth import get_user_model
from django.db.models import Q, Count, Avg
from django.db import IntegrityError # To handle duplicate list names
from django.urls import reverse # For redirects
from itertools import chain
from operator import attrgetter

def build_comment_tree(comments):
    """
    Builds a 2-level nested tree. Direct replies go on parent.replies_list.
    Replies to replies go on the reply's replies_list. Max 2 levels.
    """
    comment_map = {}
    top_level = []

    for comment in comments:
        comment.replies_list = []
        comment_map[comment.id] = comment

    for comment in comments:
        if comment.parent_id is None:
            top_level.append(comment)
        elif comment.parent_id in comment_map:
            comment_map[comment.parent_id].replies_list.append(comment)
        else:
            top_level.append(comment)

    return top_level


@login_required
def feed_view(request):
    """Displays a chronological feed including reviews, list items, shared lists, and follows."""
    followed_user_ids = list(request.user.following.values_list('followed_id', flat=True))
    user_ids_to_include = followed_user_ids + [request.user.id]

    review_ct = ContentType.objects.get_for_model(UserReview)
    usercontent_ct = ContentType.objects.get_for_model(UserContent)
    sharedlistpost_ct = ContentType.objects.get_for_model(SharedListPost)
    comment_ct = ContentType.objects.get_for_model(Comment)

    reviews = UserReview.objects.filter(
        user_id__in=user_ids_to_include
    ).select_related('user', 'user__profile')

    list_items = UserContent.objects.filter(
        user_id__in=user_ids_to_include
    ).exclude(
        list_type=UserContent.ListType.HISTORY
    ).select_related('user', 'user__profile', 'custom_list')

    shared_posts = SharedListPost.objects.filter(
        user_id__in=user_ids_to_include
    ).select_related('user', 'user__profile', 'list')

    raw_feed_items = []
    for item in reviews:
        item.type = 'review'
        item.ctype_id = review_ct.id
        item.obj_id = item.id
        item.user = item.user if hasattr(item, 'user') else None
        raw_feed_items.append(item)

    for item in list_items:
        item.type = 'list_item'
        item.ctype_id = usercontent_ct.id
        item.obj_id = item.id
        item.user = item.user if hasattr(item, 'user') else None
        raw_feed_items.append(item)

    for item in shared_posts:
        if not item.list:
            continue
        item.type = 'share'
        item.ctype_id = sharedlistpost_ct.id
        item.obj_id = item.id
        item.user = item.user if hasattr(item, 'user') else None
        raw_feed_items.append(item)

    # =====================================================
    # BUG #5 FIX: Include follow events in feed
    # The template already handles item.type == 'follow' but the
    # queryset was never fetching UserFollow objects.
    # =====================================================
    follows = UserFollow.objects.filter(
        Q(follower_id__in=user_ids_to_include) | Q(followed_id__in=user_ids_to_include)
    ).select_related(
        'follower', 'follower__profile',
        'followed', 'followed__profile'
    ).order_by('-timestamp')[:50]

    for item in follows:
        item.type = 'follow'
        item.ctype_id = None  # Follows don't have votes/comments
        item.obj_id = None
        item.user = item.follower
        raw_feed_items.append(item)

    raw_feed_items.sort(key=attrgetter('timestamp'), reverse=True)
    feed_items_limited = raw_feed_items[:50]

    # --- Pre-fetch comments, likes, and votes for feed items ---
    item_lookup = {}
    content_type_ids = set()
    object_ids_by_ctype = {}

    for item in feed_items_limited:
        # Skip follow items — they don't have comments/votes
        if item.ctype_id and item.obj_id:
            lookup_key = (item.ctype_id, item.obj_id)
            item_lookup[lookup_key] = item
            content_type_ids.add(item.ctype_id)
            if item.ctype_id not in object_ids_by_ctype:
                object_ids_by_ctype[item.ctype_id] = set()
            object_ids_by_ctype[item.ctype_id].add(item.obj_id)

            item.fetched_comments = []
            item.fetched_like_count = 0
            item.fetched_user_liked = False
            item.fetched_up_count = 0
            item.fetched_down_count = 0
            item.fetched_user_vote = 0

    if content_type_ids:
        all_object_ids = {oid for ctid in content_type_ids for oid in object_ids_by_ctype.get(ctid, set())}

        # --- Fetch comments ---
        comments_qs = Comment.objects.filter(
            content_type_id__in=content_type_ids,
            object_id__in=all_object_ids
        ).select_related('user', 'user__profile', 'parent__user').order_by('timestamp')

        comments_by_target = {}
        all_comment_ids = []
        for comment in comments_qs:
            key = (comment.content_type_id, comment.object_id)
            if key not in comments_by_target:
                comments_by_target[key] = []
            comments_by_target[key].append(comment)
            all_comment_ids.append(comment.id)

        for key, item in item_lookup.items():
            item.fetched_comments = comments_by_target.get(key, [])
            
        # Store flat count BEFORE building tree
        for key, item in item_lookup.items():
            item.fetched_comment_count = len(item.fetched_comments)
            
        # Build comment trees (converts flat list to nested)
        for key in comments_by_target:
            comments_by_target[key] = build_comment_tree(comments_by_target[key])

        # Re-assign the tree versions
        for key, item in item_lookup.items():
            item.fetched_comments = comments_by_target.get(key, [])

        # --- Fetch votes on COMMENTS ---
        if all_comment_ids:
            comment_votes_qs = Vote.objects.filter(
                content_type=comment_ct,
                object_id__in=all_comment_ids
            )

            # Upvote counts per comment
            comment_up_counts = comment_votes_qs.filter(vote_type=1).values('object_id').annotate(count=Count('id'))
            comment_up_lookup = {d['object_id']: d['count'] for d in comment_up_counts}

            # Downvote counts per comment
            comment_down_counts = comment_votes_qs.filter(vote_type=-1).values('object_id').annotate(count=Count('id'))
            comment_down_lookup = {d['object_id']: d['count'] for d in comment_down_counts}

            # User's votes on comments
            user_comment_votes = comment_votes_qs.filter(user=request.user).values_list('object_id', 'vote_type')
            user_comment_vote_lookup = {oid: vt for oid, vt in user_comment_votes}

            # Attach vote data to each comment object
            for comment_list in comments_by_target.values():
                for comment in comment_list:
                    comment.fetched_up_count = comment_up_lookup.get(comment.id, 0)
                    comment.fetched_down_count = comment_down_lookup.get(comment.id, 0)
                    comment.fetched_user_vote = user_comment_vote_lookup.get(comment.id, 0)

        # --- Fetch likes (kept for content detail compatibility) ---
        likes_qs = Like.objects.filter(
            content_type_id__in=content_type_ids,
            object_id__in=all_object_ids
        )
        likes_by_item = likes_qs.values('content_type_id', 'object_id').annotate(count=Count('id')).values('content_type_id', 'object_id', 'count')
        user_liked_items_qs = likes_qs.filter(user=request.user).values_list('content_type_id', 'object_id')
        user_liked_items = set(user_liked_items_qs)
        like_counts_lookup = {(d['content_type_id'], d['object_id']): d['count'] for d in likes_by_item}

        for key, item in item_lookup.items():
            item.fetched_like_count = like_counts_lookup.get(key, 0)
            item.fetched_user_liked = key in user_liked_items

        # --- Fetch votes on FEED ITEMS (posts) ---
        votes_qs = Vote.objects.filter(
            content_type_id__in=content_type_ids,
            object_id__in=all_object_ids
        )

        up_counts = votes_qs.filter(vote_type=1).values('content_type_id', 'object_id').annotate(count=Count('id'))
        up_lookup = {(d['content_type_id'], d['object_id']): d['count'] for d in up_counts}

        down_counts = votes_qs.filter(vote_type=-1).values('content_type_id', 'object_id').annotate(count=Count('id'))
        down_lookup = {(d['content_type_id'], d['object_id']): d['count'] for d in down_counts}

        user_votes_qs = votes_qs.filter(user=request.user).values_list('content_type_id', 'object_id', 'vote_type')
        user_votes_lookup = {(ct, oid): vt for ct, oid, vt in user_votes_qs}

        for key, item in item_lookup.items():
            item.fetched_up_count = up_lookup.get(key, 0)
            item.fetched_down_count = down_lookup.get(key, 0)
            item.fetched_user_vote = user_votes_lookup.get(key, 0)

    comment_form = CommentForm()
    comment_ctype_id = ContentType.objects.get_for_model(Comment).id

    context = {
        'feed_items': feed_items_limited,
        'comment_form': comment_form,
        'comment_ctype_id': comment_ctype_id,
    }
    return render(request, 'roulette/feed.html', context)

# This view is responsible for showing the main page of your app.
@login_required
def roulette_view(request):
    context = {
        'settings': settings
    }
    return render(request, 'roulette/roulette.html', context)


@login_required
def user_profile_view(request, username):
    User = get_user_model()
    profile_user = get_object_or_404(User, username=username)

    is_following = False
    if request.user.is_authenticated and request.user != profile_user:
        is_following = UserFollow.objects.filter(follower=request.user, followed=profile_user).exists()

    favorite_list = []
    watchlist_list = []

    is_private = profile_user.profile.is_favorites_private and request.user != profile_user

    if not is_private:
        # Keep .values() here as we only need specific fields for the grid
        favorite_list = list(UserContent.objects.filter(
            user=profile_user,
            list_type=UserContent.ListType.FAVORITE
        ).order_by('-timestamp').values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type'))

        watchlist_list = list(UserContent.objects.filter(
            user=profile_user,
            list_type=UserContent.ListType.WATCHLIST
        ).order_by('-timestamp').values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type'))

    # --- MODIFICATION: Fetch full related objects ---
    # Fetch UserFollow objects, prefetching the related user and their profile
    followers_follows = profile_user.followers.select_related('follower__profile')
    following_follows = profile_user.following.select_related('followed__profile')
    # --- END MODIFICATION ---

    followers_count = followers_follows.count() # Count directly from the queryset
    following_count = following_follows.count() # Count directly from the queryset

    user_reviews = UserReview.objects.filter(user=profile_user)

    context = {
        'profile_user': profile_user,
        'is_following': is_following,
        'favorite_list': favorite_list,
        'watchlist_list': watchlist_list,
        'is_private': is_private,
        'is_owner': request.user == profile_user,
        # --- MODIFICATION: Pass the querysets ---
        'followers_follows': followers_follows, # Pass the queryset of UserFollow objects
        'following_follows': following_follows, # Pass the queryset of UserFollow objects
        # --- END MODIFICATION ---
        'followers_count': followers_count,
        'following_count': following_count,
        'user_reviews': user_reviews,
    }

    return render(request, 'roulette/profile.html', context)

# Helper function to reduce repeated API call code
def fetch_tmdb_data(endpoint):
    base_url = "https://api.themoviedb.org/3"
    params = {"api_key": settings.TMDB_API_KEY, "language": "en-US", "page": 1}
    try:
        response = requests.get(f"{base_url}/{endpoint}", params=params)
        response.raise_for_status()
        return response.json().get('results', [])
    except requests.exceptions.RequestException as e:
        print(f"API Error fetching {endpoint}: {e}")
        return []

# --- NEW DISCOVER VIEW ---

def discover_view(request):
    context = {
        'popular_movies': fetch_tmdb_data('movie/popular'),
        'top_rated_movies': fetch_tmdb_data('movie/top_rated'),
        'popular_tv': fetch_tmdb_data('tv/popular'),
        'top_rated_tv': fetch_tmdb_data('tv/top_rated'),
    }
    return render(request, 'roulette/discover.html', context)


# --- UPDATED CONTENT DETAIL VIEW ---
@login_required
def content_detail_view(request, content_type, tmdb_id):
    BASE_URL = "https://api.themoviedb.org/3"
    endpoint_type = 'movie' if content_type == 'movie' else 'tv'
    model_content_type = UserContent.ContentType.MOVIE if content_type == 'movie' else UserContent.ContentType.TV
 
    try:
        detail_params = {
            "api_key": settings.TMDB_API_KEY,
            "append_to_response": "videos,watch/providers"
        }
        detail_res = requests.get(f"{BASE_URL}/{endpoint_type}/{tmdb_id}", params=detail_params)
        detail_res.raise_for_status()
        content_details = detail_res.json()
 
        streaming_providers = content_details.get('watch/providers', {}).get('results', {}).get('US', {}).get('flatrate', [])
 
        trailer_key = None
        videos = content_details.get('videos', {}).get('results', [])
        for video in videos:
            if video.get('site') == 'YouTube' and video.get('type') == 'Trailer':
                trailer_key = video.get('key')
                break
 
        is_favorite = UserContent.objects.filter(
            user=request.user, tmdb_id=tmdb_id, list_type=UserContent.ListType.FAVORITE,
            content_type=model_content_type
        ).exists()
 
        is_watchlist = UserContent.objects.filter(
            user=request.user, tmdb_id=tmdb_id, list_type=UserContent.ListType.WATCHLIST,
            content_type=model_content_type
        ).exists()
 
        # --- REVIEWS LOGIC ---
        all_reviews = UserReview.objects.filter(
            tmdb_id=tmdb_id, content_type=model_content_type
        ).select_related('user', 'user__profile').order_by('-timestamp')
 
        review_ctype = ContentType.objects.get_for_model(UserReview)
        comment_ctype = ContentType.objects.get_for_model(Comment)
 
        # Collect all review IDs for batch queries
        review_ids = [r.id for r in all_reviews]
 
        # --- Batch fetch votes on reviews ---
        if review_ids:
            review_votes_qs = Vote.objects.filter(content_type=review_ctype, object_id__in=review_ids)
 
            rv_up = review_votes_qs.filter(vote_type=1).values('object_id').annotate(count=Count('id'))
            rv_up_lookup = {d['object_id']: d['count'] for d in rv_up}
 
            rv_down = review_votes_qs.filter(vote_type=-1).values('object_id').annotate(count=Count('id'))
            rv_down_lookup = {d['object_id']: d['count'] for d in rv_down}
 
            rv_user = review_votes_qs.filter(user=request.user).values_list('object_id', 'vote_type')
            rv_user_lookup = {oid: vt for oid, vt in rv_user}
        else:
            rv_up_lookup = {}
            rv_down_lookup = {}
            rv_user_lookup = {}
 
        # --- Batch fetch comments on reviews ---
        if review_ids:
            comments_qs = Comment.objects.filter(
                content_type=review_ctype, object_id__in=review_ids
            ).select_related('user', 'user__profile', 'parent__user').order_by('timestamp')
 
            comments_by_review = {}
            all_comment_ids = []
            for comment in comments_qs:
                if comment.object_id not in comments_by_review:
                    comments_by_review[comment.object_id] = []
                comments_by_review[comment.object_id].append(comment)
                all_comment_ids.append(comment.id)
 
            # --- Batch fetch votes on comments ---
            if all_comment_ids:
                cv_qs = Vote.objects.filter(content_type=comment_ctype, object_id__in=all_comment_ids)
 
                cv_up = cv_qs.filter(vote_type=1).values('object_id').annotate(count=Count('id'))
                cv_up_lookup = {d['object_id']: d['count'] for d in cv_up}
 
                cv_down = cv_qs.filter(vote_type=-1).values('object_id').annotate(count=Count('id'))
                cv_down_lookup = {d['object_id']: d['count'] for d in cv_down}
 
                cv_user = cv_qs.filter(user=request.user).values_list('object_id', 'vote_type')
                cv_user_lookup = {oid: vt for oid, vt in cv_user}
 
                # Attach vote data to each comment
                for comment_list in comments_by_review.values():
                    for c in comment_list:
                        c.fetched_up_count = cv_up_lookup.get(c.id, 0)
                        c.fetched_down_count = cv_down_lookup.get(c.id, 0)
                        c.fetched_user_vote = cv_user_lookup.get(c.id, 0)
            else:
                for comment_list in comments_by_review.values():
                    for c in comment_list:
                        c.fetched_up_count = 0
                        c.fetched_down_count = 0
                        c.fetched_user_vote = 0
        else:
            comments_by_review = {}
 
        # --- Attach all fetched data to each review ---
        # Build trees for each review's comments
        comment_counts = {rid: len(clist) for rid, clist in comments_by_review.items()}

        # Build trees for each review's comments (ONCE)
        for rid in comments_by_review:
            comments_by_review[rid] = build_comment_tree(comments_by_review[rid])

        for review in all_reviews:
            review.fetched_up_count = rv_up_lookup.get(review.id, 0)
            review.fetched_down_count = rv_down_lookup.get(review.id, 0)
            review.fetched_user_vote = rv_user_lookup.get(review.id, 0)
            review.fetched_comments = comments_by_review.get(review.id, [])
            review.fetched_comment_count = comment_counts.get(review.id, 0)
 
        user_review = all_reviews.filter(user=request.user).first()
 
        avg_rating_data = all_reviews.aggregate(Avg('rating'))
        avg_rating = avg_rating_data['rating__avg']
 
        if user_review:
            review_form = ReviewForm(instance=user_review)
        else:
            review_form = ReviewForm()
 
        context = {
            'content': content_details,
            'content_type': content_type,
            'is_favorite': is_favorite,
            'is_watchlist': is_watchlist,
            'streaming_providers': streaming_providers,
            'trailer_key': trailer_key,
            'reviews': all_reviews,
            'user_review': user_review,
            'review_form': review_form,
            'avg_rating': avg_rating,
            'review_count': all_reviews.count(),
            'review_content_type_id': review_ctype.id,
            'comment_ctype_id': comment_ctype.id,
        }
        return render(request, 'roulette/content_detail.html', context)
 
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f"API request failed: {e}"}, status=500)

# --- NEW VIEW TO HANDLE REVIEW FORM ---
@login_required
@require_POST
def add_review(request, content_type, tmdb_id):
    model_content_type = UserContent.ContentType.MOVIE if content_type == 'movie' else UserContent.ContentType.TV

    # Get existing review or None
    user_review = UserReview.objects.filter(
        user=request.user, tmdb_id=tmdb_id, content_type=model_content_type
    ).first()

    form = ReviewForm(request.POST, instance=user_review) # Pass instance to update if it exists

    if form.is_valid():
        review = form.save(commit=False)
        review.user = request.user
        review.tmdb_id = tmdb_id
        review.content_type = model_content_type

        # Get title/poster from hidden form fields (or request.POST)
        review.title = request.POST.get('title', 'N/A')
        review.poster_path = request.POST.get('poster_path', '')
        review.overview = request.POST.get('overview', '')

        review.save()
        messages.success(request, 'Your review has been saved!')
    else:
        messages.error(request, 'There was an error with your rating.')

    return redirect('roulette:content_detail', content_type=content_type, tmdb_id=tmdb_id)

# --- NEW VIEW TO DELETE A REVIEW ---
@login_required
@require_POST
def delete_review(request, review_id):
    review = get_object_or_404(UserReview, id=review_id)

    # Ensure the user deleting the review is the one who wrote it
    if request.user != review.user:
        return HttpResponseForbidden("You cannot delete another user's review.")

    # Get content info before deleting to redirect back
    content_type = review.content_type.lower()
    tmdb_id = review.tmdb_id

    review.delete()
    messages.success(request, 'Your review has been deleted.')

    return redirect('roulette:content_detail', content_type=content_type, tmdb_id=tmdb_id)


@login_required
@require_POST
def toggle_follow(request):
    followed_user_id = request.POST.get('user_id')
    User = get_user_model()
    followed_user = get_object_or_404(User, id=followed_user_id)
    follower_user = request.user # Clarify variable name

    if follower_user == followed_user:
        return JsonResponse({'success': False, 'error': 'Cannot follow yourself.'}, status=400)

    follow_instance = UserFollow.objects.filter(follower=follower_user, followed=followed_user).first() # Use filter().first()

    if follow_instance:
        follow_instance.delete()
        message = f"Unfollowed {followed_user.username}."
        is_following = False
        # Optionally delete the follow notification if you want unfollows to remove it
        Notification.objects.filter(recipient=followed_user, actor=follower_user, verb='followed you').delete()
    else:
        UserFollow.objects.create(follower=follower_user, followed=followed_user)
        message = f"Now following {followed_user.username}!"
        is_following = True
        # --- Create Notification ---
        if follower_user != followed_user: # Don't notify yourself
            Notification.objects.create(
                recipient=followed_user,
                actor=follower_user,
                verb='followed you'
                # No target needed for a follow action
            )
        # --- End Notification ---

    # Get updated counts (optional but good practice if needed by JS)
    followers_count = followed_user.followers.count()
    following_count = follower_user.following.count()

    return JsonResponse({
        'success': True,
        'message': message,
        'is_following': is_following,
        'followers_count': followers_count, # Pass counts back
        'following_count': following_count
    })

@login_required
def get_random_content(request):
    BASE_URL = "https://api.themoviedb.org/3"

    content_type = request.GET.get('content_type', 'movie')
    watch_region = request.GET.get('watch_region', 'US')
    genre = request.GET.get('genre', '')
    platform = request.GET.get('with_watch_providers', '')
    year = request.GET.get('primary_release_date.gte', '1950')
    vote_average_gte = request.GET.get('vote_average_gte', '0')

    model_content_type = UserContent.ContentType.MOVIE if content_type == 'movie' else UserContent.ContentType.TV
    endpoint_type = 'movie' if content_type == 'movie' else 'tv'
    release_date_param = 'primary_release_date.gte' if content_type == 'movie' else 'first_air_date.gte'

    try:
        discover_params = {
            "api_key": settings.TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "include_adult": "false",
            "watch_region": watch_region,
            "with_watch_providers": platform,
            "with_genres": genre,
            release_date_param: f"{year}-01-01",
            "vote_count.gte": 100,
            "vote_average.gte": vote_average_gte
        }

        discover_res = requests.get(f"{BASE_URL}/discover/{endpoint_type}", params=discover_params)
        discover_res.raise_for_status()
        total_pages = discover_res.json().get('total_pages', 1)

        if total_pages == 0:
             return JsonResponse({'error': 'No content found with the selected filters.'}, status=404)

        random_page = random.randint(1, min(total_pages, 500))

        discover_params['page'] = random_page
        movies_res = requests.get(f"{BASE_URL}/discover/{endpoint_type}", params=discover_params)
        movies_res.raise_for_status()
        results = movies_res.json().get('results', [])

        if not results:
            return JsonResponse({'error': 'No content found with the selected filters.'}, status=404)

        random_content_base = random.choice(results)
        content_id = random_content_base['id']

        detail_params = {
            "api_key": settings.TMDB_API_KEY,
            "append_to_response": "videos,watch/providers"
        }
        detail_res = requests.get(f"{BASE_URL}/{endpoint_type}/{content_id}", params=detail_params)
        detail_res.raise_for_status()
        content_details = detail_res.json()

        content_details['content_type'] = content_type

        title_key = 'title' if content_type == 'movie' else 'name'
        date_key = 'release_date' if content_type == 'movie' else 'first_air_date'

        UserContent.objects.update_or_create(
            user=request.user,
            tmdb_id=content_id,
            list_type=UserContent.ListType.HISTORY,
            content_type=model_content_type,
            defaults={
                'title': content_details.get(title_key, 'N/A'),
                'poster_path': content_details.get('poster_path', ''),
                'release_year': content_details.get(date_key, '----')[:4],
                'overview': content_details.get('overview', ''),
            }
        )

        return JsonResponse(content_details)

    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f"API request failed: {e}"}, status=500)


# --- FIXED get_user_lists VIEW ---
@login_required
def get_user_lists(request):
    favorites = UserContent.objects.filter(user=request.user, list_type=UserContent.ListType.FAVORITE)
    history = UserContent.objects.filter(user=request.user, list_type=UserContent.ListType.HISTORY)
    watchlist = UserContent.objects.filter(user=request.user, list_type=UserContent.ListType.WATCHLIST)

    # --- ADD THIS ---
    custom_lists = UserList.objects.filter(user=request.user).values('id', 'name') # Get IDs and names

    tmdb_id = request.GET.get('tmdb_id')
    content_type_str = request.GET.get('content_type')

    is_favorite = False
    is_watchlist = False
    if tmdb_id and content_type_str:
        try:
            tmdb_id_int = int(tmdb_id)
            model_content_type = UserContent.ContentType.MOVIE if content_type_str == 'movie' else UserContent.ContentType.TV
            is_favorite = favorites.filter(tmdb_id=tmdb_id_int, content_type=model_content_type).exists()
            is_watchlist = watchlist.filter(tmdb_id=tmdb_id_int, content_type=model_content_type).exists()
        except ValueError:
            pass

    return JsonResponse({
        'favorites': list(favorites.values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type')),
        'history': list(history.values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type')),
        'watchlist': list(watchlist.values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type')),
        # --- ADD CUSTOM LISTS TO RESPONSE ---
        'custom_lists': list(custom_lists),
        # --- END ADD ---
        'is_favorite': is_favorite,
        'is_watchlist': is_watchlist,
    })

# --- FIXED toggle_favorite VIEW ---
@login_required
@require_POST
def toggle_favorite(request):
    tmdb_id = request.POST.get('tmdb_id')
    content_type_str = request.POST.get('content_type')

    # Basic validation for essential IDs
    if not tmdb_id or not content_type_str:
         return JsonResponse({'success': False, 'error': 'Missing content ID or type.'}, status=400)

    model_content_type = UserContent.ContentType.MOVIE if content_type_str == 'movie' else UserContent.ContentType.TV

    try:
        favorite_instance = UserContent.objects.get(
            user=request.user,
            tmdb_id=tmdb_id,
            list_type=UserContent.ListType.FAVORITE,
            content_type=model_content_type
        )
        # If it exists, delete it.
        favorite_instance.delete()
        is_favorite = False
    except UserContent.DoesNotExist:
        # If it does not exist, create it.
        title = request.POST.get('title')
        poster_path = request.POST.get('poster_path', '')
        release_year = request.POST.get('release_year')

        if not title or not release_year:
            return JsonResponse({'success': False, 'error': 'Missing title or year for new favorite.'}, status=400)

        UserContent.objects.create(
            user=request.user,
            tmdb_id=tmdb_id,
            list_type=UserContent.ListType.FAVORITE,
            content_type=model_content_type,
            title=title,
            poster_path=poster_path,
            release_year=release_year,
            overview=request.POST.get('overview', ''),
        )
        is_favorite = True

    return JsonResponse({'success': True, 'is_favorite': is_favorite})


@login_required
@require_POST
def toggle_watchlist(request):
    tmdb_id = request.POST.get('tmdb_id')
    content_type_str = request.POST.get('content_type')

    if not tmdb_id or not content_type_str:
         return JsonResponse({'success': False, 'error': 'Missing content ID or type.'}, status=400)

    model_content_type = UserContent.ContentType.MOVIE if content_type_str == 'movie' else UserContent.ContentType.TV

    try:
        watchlist_instance = UserContent.objects.get(
            user=request.user,
            tmdb_id=tmdb_id,
            list_type=UserContent.ListType.WATCHLIST,
            content_type=model_content_type
        )
        # If it exists, delete it.
        watchlist_instance.delete()
        is_watchlist = False
    except UserContent.DoesNotExist:
        # If it does not exist, create it.
        title = request.POST.get('title')
        poster_path = request.POST.get('poster_path', '')
        release_year = request.POST.get('release_year')

        if not title or not release_year:
            return JsonResponse({'success': False, 'error': 'Missing title or year for new item.'}, status=400)

        UserContent.objects.create(
            user=request.user,
            tmdb_id=tmdb_id,
            list_type=UserContent.ListType.WATCHLIST,
            content_type=model_content_type,
            title=title,
            poster_path=poster_path,
            release_year=release_year,
            overview=request.POST.get('overview', ''),
        )
        is_watchlist = True

    return JsonResponse({'success': True, 'is_watchlist': is_watchlist})

from django.db.models import Q, Count, Exists, OuterRef
from django.contrib.auth import get_user_model
from .models import UserFollow  # Ensure this import matches your project structure

@login_required
def search_view(request):
    query = request.GET.get('q', '')
    active_tab = request.GET.get('type', 'all')  # Default to 'all'
    
    user_results = get_user_model().objects.none()
    content_results = []
    movie_results = []
    tv_results = []

    if query:
        # 1. Always fetch users for the 'People' tab or 'All' summary
        user_results = get_user_model().objects.filter(
            Q(username__icontains=query)
        ).annotate(
            follower_count=Count('followers', distinct=True)
        ).select_related('profile')

        if request.user.is_authenticated:
            for u in user_results:
                u.is_followed = UserFollow.objects.filter(follower=request.user, followed=u).exists()

        # 2. Fetch TMDB results
        try:
            search_url = "https://api.themoviedb.org/3/search/multi"
            params = {"api_key": settings.TMDB_API_KEY, "query": query, "language": "en-US"}
            res = requests.get(search_url, params=params)
            res.raise_for_status()
            api_data = res.json().get('results', [])

            # Categorize the data
            movie_results = [i for i in api_data if i.get('media_type') == 'movie']
            tv_results = [i for i in api_data if i.get('media_type') == 'tv']
            
            # For the 'All' tab, show a mix
            if active_tab == 'all':
                content_results = movie_results[:10] + tv_results[:5]
            elif active_tab == 'movies':
                content_results = movie_results
            elif active_tab == 'tv':
                content_results = tv_results
                
        except Exception as e:
            print(f"API Error: {e}")

    context = {
        'user_results': user_results,
        'content_results': content_results,
        'movie_count': len(movie_results),
        'tv_count': len(tv_results),
        'people_count': user_results.count(),
        'query': query,
        'active_tab': active_tab,
    }
    return render(request, 'roulette/search_results.html', context)

@login_required
def list_all_lists_view(request):
    """Displays all custom lists for the logged-in user and a form to create new lists."""
    user_lists = UserList.objects.filter(user=request.user)
    form = UserListForm()
    context = {
        'lists': user_lists,
        'form': form,
    }
    return render(request, 'roulette/list_all.html', context)

@login_required
@require_POST # This view only handles form submission
def create_list_view(request):
    """Handles the creation of a new custom list. Returns JSON."""
    form = UserListForm(request.POST)
    if form.is_valid():
        try:
            new_list = form.save(commit=False)
            new_list.user = request.user
            new_list.save()
            # Return success and the new list's info
            return JsonResponse({
                'success': True,
                'message': f"List '{new_list.name}' created.",
                'list': {'id': new_list.id, 'name': new_list.name} # Send back new list data
            })
        except IntegrityError:
            # Return error for duplicate name
            return JsonResponse({
                'success': False,
                'error': f"You already have a list named '{form.cleaned_data['name']}'."
            }, status=400) # Use 400 Bad Request status
    else:
        # Return error for invalid form data
        error_message = "Could not create list. "
        for field, errors in form.errors.items():
             error_message += f"{field}: {', '.join(errors)} "
        return JsonResponse({'success': False, 'error': error_message.strip()}, status=400)

@login_required
def list_detail_view(request, list_id):
    try:
        user_list = UserList.objects.select_related('user', 'user__profile').get(id=list_id)
    except UserList.DoesNotExist:
        raise Http404("List not found.") # Corrected Http404 usage

    is_owner = user_list.user == request.user

    # If the list is private and the current user is not the owner, show a specific template
    if not is_owner and not user_list.is_public:
        return render(request, 'roulette/private_list.html', {'list_owner': user_list.user}, status=403)

    # --- Fetch items, form, URLs etc. ---
    list_items = UserContent.objects.filter(
        custom_list=user_list,
        list_type=UserContent.ListType.CUSTOM
    ).order_by('-timestamp')

    share_form = ShareListForm()

    try:
        list_relative_url = user_list.get_absolute_url()
        list_absolute_url = request.build_absolute_uri(list_relative_url)
    except Exception as e:
        print(f"Error building absolute URL for list {list_id}: {e}")
        list_absolute_url = ""

    # Anyone who can view this page (passed the privacy check above) can share.
    can_share = True

    context = {
        'list': user_list,
        'items': list_items,
        'is_owner': is_owner,
        'share_form': share_form,
        'list_absolute_url': list_absolute_url,
        'can_share': can_share, # Pass the updated variable
    }
    return render(request, 'roulette/list_detail.html', context)

@login_required
@require_POST # Use POST for deletion to prevent accidental deletion via GET
def delete_list_view(request, list_id):
    """Deletes a custom list. Handles AJAX."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    user_list = get_object_or_404(UserList, id=list_id, user=request.user)
    list_name = user_list.name # Get name before deleting

    try:
        user_list.delete()
        success_message = f"List '{list_name}' deleted successfully."
        if is_ajax:
            return JsonResponse({'success': True, 'message': success_message})
        else:
            messages.success(request, success_message)
            return redirect('roulette:list_all')
    except Exception as e:
        error_message = f"An error occurred while deleting list: {e}"
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_message}, status=500)
        else:
            messages.error(request, error_message)
            return redirect('roulette:list_all')

@login_required
@require_POST
def add_to_custom_list_view(request):
    """API endpoint to add a movie/show to a custom list."""
    list_id = request.POST.get('list_id')
    tmdb_id = request.POST.get('tmdb_id')
    content_type_str = request.POST.get('content_type')
    title = request.POST.get('title')
    poster_path = request.POST.get('poster_path', '')
    release_year = request.POST.get('release_year')

    if not all([list_id, tmdb_id, content_type_str, title, release_year]):
         return JsonResponse({'success': False, 'error': 'Missing required data.'}, status=400)

    user_list = get_object_or_404(UserList, id=list_id, user=request.user)
    model_content_type = UserContent.ContentType.MOVIE if content_type_str == 'movie' else UserContent.ContentType.TV

    # Check if item already exists in this specific list
    item_exists = UserContent.objects.filter(
        user=request.user,
        tmdb_id=tmdb_id,
        content_type=model_content_type,
        list_type=UserContent.ListType.CUSTOM,
        custom_list=user_list
    ).exists()

    if item_exists:
        return JsonResponse({'success': False, 'error': f"'{title}' is already in the list '{user_list.name}'."}, status=400)

    # Create the item linked to the custom list
    UserContent.objects.create(
        user=request.user,
        tmdb_id=tmdb_id,
        list_type=UserContent.ListType.CUSTOM, # Set type to CUSTOM
        custom_list=user_list, # Link to the UserList object
        content_type=model_content_type,
        title=title,
        poster_path=poster_path,
        release_year=release_year,
        overview=request.POST.get('overview', ''),
    )

    return JsonResponse({'success': True, 'message': f"Added '{title}' to '{user_list.name}'."})

@login_required
@require_POST
def remove_from_custom_list_view(request):
    """API endpoint to remove an item from a custom list."""
    item_id = request.POST.get('item_id') # We'll use the UserContent item's own ID

    if not item_id:
        return JsonResponse({'success': False, 'error': 'Missing item ID.'}, status=400)

    list_item = get_object_or_404(UserContent, id=item_id, user=request.user, list_type=UserContent.ListType.CUSTOM)

    list_name = list_item.custom_list.name # Get name before deleting
    item_title = list_item.title
    list_item.delete()

    return JsonResponse({'success': True, 'message': f"Removed '{item_title}' from '{list_name}'."})

@login_required
@require_POST
def add_comment_view(request):
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
 
    form = CommentForm(request.POST)
    content_type_id = request.POST.get('content_type_id')
    object_id = request.POST.get('object_id')
    parent_id = request.POST.get('parent_id')  # NEW: optional parent
 
    if form.is_valid() and content_type_id and object_id:
        try:
            content_type = ContentType.objects.get_for_id(content_type_id)
            target_object = content_type.get_object_for_this_type(pk=object_id)
 
            comment = form.save(commit=False)
            comment.user = request.user
            comment.content_type = content_type
            comment.object_id = object_id
 
            # NEW: Set parent if replying to a comment
            if parent_id:
                try:
                    parent_comment = Comment.objects.get(id=parent_id)
                    # Enforce max 2 levels: if parent already has a parent,
                    # attach reply to the parent's parent (flatten to level 2)
                    comment.parent = parent_comment
                except Comment.DoesNotExist:
                    pass  # Invalid parent, save as top-level
 
            comment.save()
 
            # --- Create Notification ---
            recipient = None
            if parent_id and comment.parent:
                # Notify the person being replied to
                recipient = comment.parent.user
            elif hasattr(target_object, 'user'):
                recipient = target_object.user
 
            if recipient and recipient != request.user:
                verb = 'replied to your comment' if comment.parent else 'commented on'
                Notification.objects.create(
                    recipient=recipient,
                    actor=request.user,
                    verb=verb,
                    target_content_type=content_type,
                    target_object_id=object_id
                )
 
            if is_ajax:
                # Determine depth for template rendering
                comment_html = render_to_string(
                    'roulette/_comment.html',
                    {'comment': comment, 'request': request, 'is_reply': bool(comment.parent)}
                )
                return JsonResponse({
                    'success': True,
                    'comment_html': comment_html,
                    'parent_id': comment.parent_id,
                })
            else:
                messages.success(request, "Comment added.")
                return redirect(request.POST.get('next', 'roulette:feed'))
 
        except (ContentType.DoesNotExist, ValueError) as e:
            error_msg = f"Could not add comment: Invalid target. {e}"
            if is_ajax:
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            else:
                messages.error(request, error_msg)
        except Exception as e:
            error_msg = f"An unexpected error occurred: {e}"
            print(f"ERROR in add_comment_view: {error_msg}")
            if is_ajax:
                return JsonResponse({'success': False, 'error': "An unexpected error occurred."}, status=500)
            else:
                messages.error(request, "An unexpected error occurred.")
    else:
        error_msg = "Could not add comment."
        if not content_type_id or not object_id:
            error_msg = "Missing target information."
        elif form.errors:
            error_msg = "Please correct the errors below."
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg, 'form_errors': form.errors if form.errors else None}, status=400)
        else:
            messages.error(request, error_msg)
 
    return redirect(request.POST.get('next', 'roulette:feed'))

# --- VIEW FOR TOGGLING LIKES (AJAX) ---
@login_required
@require_POST
def toggle_like_view(request):
    content_type_id = request.POST.get('content_type_id')
    object_id = request.POST.get('object_id')

    if not content_type_id or not object_id:
        return JsonResponse({'success': False, 'error': 'Missing data'}, status=400)

    try:
        content_type = ContentType.objects.get_for_id(content_type_id)
        target_object = content_type.get_object_for_this_type(pk=object_id) # Get the actual object

        like_obj, created = Like.objects.get_or_create(
            user=request.user,
            content_type=content_type,
            object_id=object_id
        )

        user_liked = True
        recipient = None # Define recipient outside the if/else

        if not created:
            # Unlike: Delete the like and potentially the notification
            like_obj.delete()
            user_liked = False
            # Find and delete the corresponding notification
            Notification.objects.filter(
                # recipient should be the owner of the target_object
                actor=request.user,
                verb='liked',
                target_content_type=content_type,
                target_object_id=object_id
            ).delete()
        else:
            # Like: Create the notification
            user_liked = True
            # Determine the recipient (owner of the review or list item)
            if hasattr(target_object, 'user'):
                recipient = target_object.user
                if recipient != request.user: # Don't notify yourself
                     Notification.objects.create(
                        recipient=recipient,
                        actor=request.user,
                        verb='liked',
                        target_content_type=content_type,
                        target_object_id=object_id
                    )

        like_count = Like.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).count()

        return JsonResponse({'success': True, 'user_liked': user_liked, 'like_count': like_count})

    except ContentType.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid content type'}, status=400)
    except Exception as e: # Catch potential errors getting target_object
         return JsonResponse({'success': False, 'error': f'An error occurred: {e}'}, status=500)
     
@login_required
@require_POST # Ensure only POST requests can delete
def delete_comment_view(request, comment_id):
    """Deletes a comment if the logged-in user is the author. Handles AJAX."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    comment = get_object_or_404(Comment, id=comment_id)

    if request.user != comment.user:
        error_msg = "You are not authorized to delete this comment."
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=403)
        else:
            messages.error(request, error_msg)
            # Consider redirecting to feed or previous page for non-AJAX forbidden
            return redirect('roulette:feed') # Or HttpResponseForbidden(...)

    try:
        comment.delete()
        if is_ajax:
            return JsonResponse({'success': True})
        else:
            messages.success(request, "Comment deleted successfully.")
            # Redirect back for non-AJAX
            return redirect(request.POST.get('next', 'roulette:feed'))
    except Exception as e:
        # Catch potential deletion errors
        error_msg = f"An error occurred while deleting: {e}"
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=500)
        else:
            messages.error(request, error_msg)
            return redirect(request.POST.get('next', 'roulette:feed'))
        
@login_required
def notifications_view(request):
    """Displays notifications for the logged-in user and marks them as read."""
    # Fetch notifications first
    notifications = request.user.notifications.all() # Or Notification.objects.filter(recipient=request.user)

    # Mark unread notifications as read *after* fetching them for display
    unread_notifications = notifications.filter(read=False)
    unread_notifications.update(read=True) # Update the 'read' status in the database

    context = {
        'notifications': notifications # Pass the original queryset to the template
    }
    return render(request, 'roulette/notifications.html', context)

@login_required
@require_POST # Ensure only POST requests
def toggle_list_public_view(request, list_id):
    """Toggles the is_public status of a user's list via AJAX."""
    user_list = get_object_or_404(UserList, id=list_id, user=request.user) # Ensure ownership

    user_list.is_public = not user_list.is_public
    user_list.save(update_fields=['is_public', 'updated_at']) # Save efficiently

    return JsonResponse({
        'success': True,
        'is_public': user_list.is_public,
        'message': f"List '{user_list.name}' is now {'public' if user_list.is_public else 'private'}."
    })
    
@login_required
@require_POST # Ensure only POST requests
def share_list_to_feed_view(request, list_id):
    """Shares a custom list. Handles AJAX and standard POST."""
    user_list = get_object_or_404(UserList, id=list_id, user=request.user)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    # Optional: Check if public (uncomment if needed)
    if not user_list.is_public:
        error_msg = 'Only public lists can be shared.'
        if is_ajax:
            return JsonResponse({'success': False, 'error': error_msg}, status=400)
        else:
            messages.error(request, error_msg)
            return redirect(user_list.get_absolute_url())

    form = ShareListForm(request.POST)
    final_share_message = None

    if form.is_valid():
        message_from_form = form.cleaned_data.get('message', '').strip()
        if message_from_form:
             final_share_message = message_from_form

    try:
        # Create the SharedListPost object
        SharedListPost.objects.create(
            user=request.user,
            list=user_list,
            message=final_share_message
        )

        success_msg = f"List '{user_list.name}' shared to your feed."
        if is_ajax:
            # Return JSON for JavaScript toast
            return JsonResponse({'success': True, 'message': success_msg})
        else:
            # Fallback for non-JS: Use Django messages and redirect
            messages.success(request, success_msg)
            return redirect(user_list.get_absolute_url())

    except Exception as e:
        # Catch potential errors during creation
        print(f"Error sharing list {list_id}: {e}") # Log the error
        error_msg = "An unexpected error occurred while sharing the list."
        if is_ajax:
             return JsonResponse({'success': False, 'error': error_msg}, status=500)
        else:
             messages.error(request, error_msg)
             return redirect(user_list.get_absolute_url())
         
@login_required
@require_POST
def toggle_vote_view(request):
    """Handle upvote/downvote on feed items. AJAX only."""
    content_type_id = request.POST.get('content_type_id')
    object_id = request.POST.get('object_id')
    vote_type_str = request.POST.get('vote_type')  # '1' for up, '-1' for down
 
    if not content_type_id or not object_id or vote_type_str not in ('1', '-1'):
        return JsonResponse({'success': False, 'error': 'Invalid data.'}, status=400)
 
    vote_type = int(vote_type_str)
 
    try:
        content_type = ContentType.objects.get_for_id(content_type_id)
        existing_vote = Vote.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=object_id
        ).first()
 
        if existing_vote:
            if existing_vote.vote_type == vote_type:
                # Same vote again = remove it (toggle off)
                existing_vote.delete()
                user_vote = 0
            else:
                # Switch vote direction
                existing_vote.vote_type = vote_type
                existing_vote.save(update_fields=['vote_type'])
                user_vote = vote_type
        else:
            # New vote
            Vote.objects.create(
                user=request.user,
                content_type=content_type,
                object_id=object_id,
                vote_type=vote_type
            )
            user_vote = vote_type
 
        # Count upvotes and downvotes separately
        up_count = Vote.objects.filter(
            content_type=content_type, object_id=object_id, vote_type=1
        ).count()
        down_count = Vote.objects.filter(
            content_type=content_type, object_id=object_id, vote_type=-1
        ).count()
 
        return JsonResponse({
            'success': True,
            'user_vote': user_vote,  # 1, -1, or 0 (no vote)
            'up_count': up_count,
            'down_count': down_count,
        })
 
    except ContentType.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid content type.'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
@login_required
@require_POST
def edit_comment_view(request, comment_id):
    """Edit a comment's text. AJAX only."""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    comment = get_object_or_404(Comment, id=comment_id)
 
    if request.user != comment.user:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Not authorized.'}, status=403)
        return HttpResponseForbidden("Not authorized.")
 
    new_text = request.POST.get('text', '').strip()
    if not new_text:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Comment cannot be empty.'}, status=400)
        messages.error(request, 'Comment cannot be empty.')
        return redirect('roulette:feed')
 
    if len(new_text) > 500:
        if is_ajax:
            return JsonResponse({'success': False, 'error': 'Comment too long (max 500 characters).'}, status=400)
        messages.error(request, 'Comment too long.')
        return redirect('roulette:feed')
 
    comment.text = new_text
    comment.save(update_fields=['text'])
 
    if is_ajax:
        return JsonResponse({'success': True, 'text': comment.text})
    messages.success(request, 'Comment updated.')
    return redirect(request.POST.get('next', 'roulette:feed'))