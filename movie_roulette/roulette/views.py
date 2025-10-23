# movie_roulette/roulette/views.py

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.template.loader import render_to_string
from django.contrib.auth.decorators import login_required
from django.conf import settings
import requests
from django.contrib.contenttypes.models import ContentType
from .forms import UserListForm, ReviewForm, CommentForm # Add CommentForm
from .models import UserContent, UserFollow, UserList, UserReview, Comment, Like # Add Comment, Like
import random
# --- Import ReviewForm and UserReview ---
from django.contrib.auth import get_user_model
from django.db.models import Q, Count, Avg
from django.db import IntegrityError # To handle duplicate list names
from django.urls import reverse # For redirects

# --- ADDED FOR SOCIAL FEED ---
from itertools import chain
from operator import attrgetter
# --- END ADDED ---

# --- UPDATED VIEW FOR SOCIAL FEED ---
@login_required
def feed_view(request):
    """Displays a chronological feed with comments and likes, excluding history and follows.""" # Updated docstring

    followed_user_ids = list(request.user.following.values_list('followed_id', flat=True))
    user_ids_to_include = followed_user_ids + [request.user.id]

    review_ct = ContentType.objects.get_for_model(UserReview)
    usercontent_ct = ContentType.objects.get_for_model(UserContent)

    # Fetch main items
    reviews = UserReview.objects.filter(
        user_id__in=user_ids_to_include
    ).select_related('user', 'user__profile')

    list_items = UserContent.objects.filter(
        user_id__in=user_ids_to_include
    ).exclude(
        list_type=UserContent.ListType.HISTORY
    ).select_related('user', 'user__profile', 'custom_list')

    # --- REMOVE OR COMMENT OUT THESE LINES ---
    # follows = UserFollow.objects.filter(
    #     follower_id__in=user_ids_to_include
    # ).select_related('follower', 'follower__profile', 'followed', 'followed__profile')
    # --- END REMOVAL ---

    # Combine and add type/generic relation info
    raw_feed_items = []
    for item in reviews:
        item.type = 'review'
        item.ctype_id = review_ct.id
        item.obj_id = item.id
        raw_feed_items.append(item)

    for item in list_items:
        item.type = 'list_item'
        item.ctype_id = usercontent_ct.id
        item.obj_id = item.id
        raw_feed_items.append(item)

    # --- REMOVE OR COMMENT OUT THIS LOOP ---
    # for item in follows:
    #     item.type = 'follow'
    #     item.ctype_id = None # Follows don't link to Comment/Like directly
    #     item.obj_id = None
    #     raw_feed_items.append(item)
    # --- END REMOVAL ---

    raw_feed_items.sort(key=attrgetter('timestamp'), reverse=True)
    feed_items_limited = raw_feed_items[:50] # Limit to 50 most recent combined items

    # Pre-fetch comments and likes logic remains the same
    item_lookup = {}
    content_type_ids = set()
    object_ids_by_ctype = {}

    for item in feed_items_limited:
        # --- ADDED CHECK: Ensure item has ctype_id and obj_id before processing for comments/likes ---
        if item.ctype_id and item.obj_id:
            item_lookup[item.obj_id] = item # Use obj_id as key since it's unique within its type
            content_type_ids.add(item.ctype_id)
            if item.ctype_id not in object_ids_by_ctype:
                object_ids_by_ctype[item.ctype_id] = set()
            object_ids_by_ctype[item.ctype_id].add(item.obj_id)
            item.comments = [] # Initialize comments list
            item.like_count = 0 # Initialize like count
            item.user_liked = False # Initialize user liked status
    # --- END CHECK ---

    # --- Fetching comments based on the filtered items ---
    comments_qs = Comment.objects.filter(
        content_type_id__in=content_type_ids # Use the collected content type IDs
    ).select_related('user', 'user__profile')

    all_comments = []
    for ct_id, obj_ids in object_ids_by_ctype.items():
         # Fetch comments only for the object IDs relevant to this content type
        all_comments.extend(list(comments_qs.filter(content_type_id=ct_id, object_id__in=obj_ids)))

    # --- Assign comments to their respective items ---
    for comment in all_comments:
         # Use obj_id for lookup
        if comment.object_id in item_lookup and hasattr(item_lookup[comment.object_id], 'comments'):
             item_lookup[comment.object_id].comments.append(comment)


    # --- Fetching likes based on the filtered items ---
    likes_qs = Like.objects.filter(
        content_type_id__in=content_type_ids # Use the collected content type IDs
    )
    all_likes = []
    for ct_id, obj_ids in object_ids_by_ctype.items():
        # Fetch likes only for the object IDs relevant to this content type
        all_likes.extend(list(likes_qs.filter(content_type_id=ct_id, object_id__in=obj_ids)))


    # --- Calculate like counts and user liked status ---
    likes_by_item = {} # Key: obj_id, Value: count
    user_liked_items = set() # Set of obj_ids liked by the current user

    for like in all_likes:
         # Use obj_id for lookup
         if like.object_id in item_lookup:
            likes_by_item[like.object_id] = likes_by_item.get(like.object_id, 0) + 1
            if like.user_id == request.user.id:
                user_liked_items.add(like.object_id)


    # --- Assign like data to feed items ---
    for obj_id, item in item_lookup.items():
         if hasattr(item, 'like_count'): # Check if attribute exists before assigning
            item.like_count = likes_by_item.get(obj_id, 0)
            item.user_liked = obj_id in user_liked_items

    # --- End pre-fetching logic ---


    comment_form = CommentForm()

    context = {
        'feed_items': feed_items_limited,
        'comment_form': comment_form,
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
        favorite_list = list(UserContent.objects.filter(
            user=profile_user,
            list_type=UserContent.ListType.FAVORITE
        ).order_by('-timestamp').values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type'))

        watchlist_list = list(UserContent.objects.filter(
            user=profile_user,
            list_type=UserContent.ListType.WATCHLIST
        ).order_by('-timestamp').values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type'))

    followers_list = profile_user.followers.select_related('follower').values('follower__username', 'follower__id')
    following_list = profile_user.following.select_related('followed').values('followed__username', 'followed__id')

    followers_count = followers_list.count()
    following_count = following_list.count()

    # --- ADDED: Get user's reviews ---
    user_reviews = UserReview.objects.filter(user=profile_user)
    # --- END ADDED ---

    context = {
        'profile_user': profile_user,
        'is_following': is_following,
        'favorite_list': favorite_list,
        'watchlist_list': watchlist_list,
        'is_private': is_private,
        'is_owner': request.user == profile_user,
        'followers_list': list(followers_list),
        'following_list': list(following_list),
        'followers_count': followers_count,
        'following_count': following_count,
        'user_reviews': user_reviews, # <-- Add to context
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
@login_required
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

        # Safely access the nested provider data
        streaming_providers = content_details.get('watch/providers', {}).get('results', {}).get('US', {}).get('flatrate', [])

        # Find the YouTube trailer key
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

        # --- ADDED FOR REVIEWS ---
        all_reviews = UserReview.objects.filter(
            tmdb_id=tmdb_id, content_type=model_content_type
        ).select_related('user', 'user__profile').order_by('-timestamp')

        user_review = all_reviews.filter(user=request.user).first()

        # Calculate average rating
        avg_rating_data = all_reviews.aggregate(Avg('rating'))
        avg_rating = avg_rating_data['rating__avg']

        if user_review:
            # If user already has a review, pre-fill the form
            review_form = ReviewForm(instance=user_review)
        else:
            review_form = ReviewForm()
        # --- END ADDED ---

        context = {
            'content': content_details,
            'content_type': content_type,
            'is_favorite': is_favorite,
            'is_watchlist': is_watchlist,
            'streaming_providers': streaming_providers,
            'trailer_key': trailer_key,
            # --- ADDED TO CONTEXT ---
            'reviews': all_reviews,
            'user_review': user_review,
            'review_form': review_form,
            'avg_rating': avg_rating,
            'review_count': all_reviews.count(),
            # --- END ADDED ---
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

    if request.user == followed_user:
        return JsonResponse({'success': False, 'error': 'Cannot follow yourself.'}, status=400)

    try:
        follow_instance = UserFollow.objects.get(follower=request.user, followed=followed_user)
        follow_instance.delete()
        # --- UPDATED: 'is_following' added ---
        message = f"Unfollowed {followed_user.username}."
        is_following = False
    except UserFollow.DoesNotExist:
        UserFollow.objects.create(follower=request.user, followed=followed_user)
        message = f"Now following {followed_user.username}!"
        is_following = True

    return JsonResponse({'success': True, 'message': message, 'is_following': is_following})

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
            "with_genres": genre, # 'mood_genre' has been removed
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
            }
        )

        return JsonResponse(content_details)

    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f"API request failed: {e}"}, status=500)

    # The duplicate code block has been removed from here

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

    # This is the new, more robust logic
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
        # Get the rest of the data needed for creation.
        title = request.POST.get('title')
        poster_path = request.POST.get('poster_path', '')
        release_year = request.POST.get('release_year')

        # Check that we have the data needed to create a new favorite
        if not title or not release_year:
            return JsonResponse({'success': False, 'error': 'Missing title or year for new favorite.'}, status=400)

        UserContent.objects.create(
            user=request.user,
            tmdb_id=tmdb_id,
            list_type=UserContent.ListType.FAVORITE,
            content_type=model_content_type,
            title=title,
            poster_path=poster_path,
            release_year=release_year
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
            release_year=release_year
        )
        is_watchlist = True

    return JsonResponse({'success': True, 'is_watchlist': is_watchlist})

@login_required
def search_view(request):
    query = request.GET.get('q')
    user_results = get_user_model().objects.none()
    content_results = []

    if query:
        # --- ADDED: Prefetch profile for profile picture ---
        user_results = get_user_model().objects.filter(
            Q(username__icontains=query)
        ).annotate(
            follower_count=Count('followers') # Creates a new field 'follower_count'
        ).select_related('profile') # --- ADDED

        try:
            search_url = "https://api.themoviedb.org/3/search/multi"
            params = {
                "api_key": settings.TMDB_API_KEY, "query": query, "include_adult": "false",
                "language": "en-US", "page": 1
            }
            res = requests.get(search_url, params=params)
            res.raise_for_status()
            api_data = res.json()
            content_results = [
                item for item in api_data.get('results', [])
                if item.get('media_type') in ['movie', 'tv']
            ]
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")

    context = {
        'user_results': user_results,
        'content_results': content_results,
        'query': query,
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
    """Displays the items within a specific custom list."""
    user_list = get_object_or_404(UserList, id=list_id, user=request.user) # Ensure user owns list

    # Get items associated with this specific list
    list_items = UserContent.objects.filter(
        custom_list=user_list,
        list_type=UserContent.ListType.CUSTOM
    ).order_by('-timestamp')

    context = {
        'list': user_list,
        'items': list_items,
    }
    return render(request, 'roulette/list_detail.html', context)

@login_required
@require_POST # Use POST for deletion to prevent accidental deletion via GET
def delete_list_view(request, list_id):
    """Deletes a custom list."""
    user_list = get_object_or_404(UserList, id=list_id, user=request.user) # Ensure user owns list
    list_name = user_list.name
    user_list.delete()
    messages.success(request, f"List '{list_name}' deleted successfully.")
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
        release_year=release_year
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
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' # Check if AJAX

    form = CommentForm(request.POST)
    content_type_id = request.POST.get('content_type_id')
    object_id = request.POST.get('object_id')

    if form.is_valid() and content_type_id and object_id:
        try:
            content_type = ContentType.objects.get_for_id(content_type_id)
            # Optional content type checking here...

            comment = form.save(commit=False)
            comment.user = request.user
            comment.content_type = content_type
            comment.object_id = object_id
            comment.save()

            if is_ajax:
                # Render the single comment template fragment
                comment_html = render_to_string(
                    'roulette/_comment.html',
                    {'comment': comment, 'request': request} # Pass request for user check in fragment
                )
                return JsonResponse({'success': True, 'comment_html': comment_html})
            else:
                messages.success(request, "Comment added.")
                # Non-AJAX fallback redirect
                return redirect(request.POST.get('next', 'roulette:feed')) # Use 'next' if provided, else feed

        except (ContentType.DoesNotExist, ValueError) as e:
            error_msg = f"Could not add comment: Invalid target. {e}"
            if is_ajax:
                return JsonResponse({'success': False, 'error': error_msg}, status=400)
            else:
                messages.error(request, error_msg)
        except Exception as e:
            error_msg = f"An unexpected error occurred: {e}"
            if is_ajax:
                return JsonResponse({'success': False, 'error': error_msg}, status=500)
            else:
                messages.error(request, error_msg)
    else:
        # Form is invalid or missing IDs
        error_msg = "Could not add comment."
        if not content_type_id or not object_id:
            error_msg = "Missing target information."
        elif form.errors:
             # Make form errors JSON serializable for AJAX response
             form_errors = {field: [e for e in errors] for field, errors in form.errors.items()}
             error_msg = f"Please correct the errors below."

        if is_ajax:
            return JsonResponse({
                'success': False,
                'error': error_msg,
                'form_errors': form.errors if form.errors else None # Send specific field errors
            }, status=400)
        else:
            messages.error(request, error_msg)
            # You might want to re-render the feed page with the invalid form here for non-AJAX
            # This part is slightly trickier without AJAX, often just redirecting is simpler.

    # Default fallback redirect for non-AJAX errors
    return redirect(request.POST.get('next', 'roulette:feed'))

# --- NEW VIEW FOR TOGGLING LIKES (AJAX) ---
@login_required
@require_POST
def toggle_like_view(request):
    content_type_id = request.POST.get('content_type_id')
    object_id = request.POST.get('object_id')

    if not content_type_id or not object_id:
        return JsonResponse({'success': False, 'error': 'Missing data'}, status=400)

    try:
        content_type = ContentType.objects.get_for_id(content_type_id)
        # Optional: Check if the content_type is one we allow likes on
        # target_model = content_type.model_class()
        # if target_model not in [UserReview, UserContent]:
        #     raise ValueError("Invalid content type for likes")

        like_obj, created = Like.objects.get_or_create(
            user=request.user,
            content_type=content_type,
            object_id=object_id
        )

        user_liked = True
        if not created:
            # If get_or_create found an existing like, delete it (unlike)
            like_obj.delete()
            user_liked = False

        # Get the new total like count for this item
        like_count = Like.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).count()

        return JsonResponse({'success': True, 'user_liked': user_liked, 'like_count': like_count})

    except ContentType.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid content type'}, status=400)
    except ValueError:
         return JsonResponse({'success': False, 'error': 'Invalid object ID'}, status=400)
    except Exception as e:
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