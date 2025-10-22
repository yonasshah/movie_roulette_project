from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.conf import settings
import requests
import random
from .models import UserContent, UserFollow
from django.contrib.auth import get_user_model
from django.db.models import Q

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
    # Check if the profile is private AND if the current user is not the owner
    is_private = profile_user.profile.is_favorites_private and request.user != profile_user
    
    if not is_private:
        favorite_list = list(UserContent.objects.filter(
            user=profile_user,
            list_type=UserContent.ListType.FAVORITE
        ).order_by('-timestamp').values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type'))

    followers_list = profile_user.followers.select_related('follower').values('follower__username', 'follower__id')
    following_list = profile_user.following.select_related('followed').values('followed__username', 'followed__id')
    
    followers_count = followers_list.count()
    following_count = following_list.count()
    
    context = {
        'profile_user': profile_user,
        'is_following': is_following,
        'favorite_list': favorite_list,
        'is_private': is_private, # Pass the privacy status to the template
        'is_owner': request.user == profile_user,
        'settings': settings,
        'followers_list': list(followers_list),
        'following_list': list(following_list),
        'followers_count': followers_count,
        'following_count': following_count,
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

# --- NEW CONTENT DETAIL VIEW ---
@login_required
@login_required
def content_detail_view(request, content_type, tmdb_id):
    BASE_URL = "https://api.themoviedb.org/3"
    endpoint_type = 'movie' if content_type == 'movie' else 'tv'
    
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
            content_type=UserContent.ContentType.MOVIE if content_type == 'movie' else UserContent.ContentType.TV
        ).exists()

        context = {
            'content': content_details,
            'content_type': content_type,
            'is_favorite': is_favorite,
            'streaming_providers': streaming_providers, # Pass cleaned data
            'trailer_key': trailer_key, # Pass just the key
            'settings': settings,
        }
        return render(request, 'roulette/content_detail.html', context)
        
    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f"API request failed: {e}"}, status=500)


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
        message = f"Unfollowed {followed_user.username}."
    except UserFollow.DoesNotExist:
        UserFollow.objects.create(follower=request.user, followed=followed_user)
        message = f"Now following {followed_user.username}!"
        
    return JsonResponse({'success': True, 'message': message})

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
    
    tmdb_id = request.GET.get('tmdb_id')
    content_type_str = request.GET.get('content_type')
    
    is_favorite = False
    if tmdb_id and content_type_str:
        model_content_type = UserContent.ContentType.MOVIE if content_type_str == 'movie' else UserContent.ContentType.TV
        is_favorite = favorites.filter(tmdb_id=tmdb_id, content_type=model_content_type).exists()

    return JsonResponse({
        'favorites': list(favorites.values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type')),
        'history': list(history.values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type')),
        'is_favorite': is_favorite,
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
def search_view(request):
    query = request.GET.get('q')
    user_results = get_user_model().objects.none()
    content_results = []

    if query:
        user_results = get_user_model().objects.filter(Q(username__icontains=query))
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