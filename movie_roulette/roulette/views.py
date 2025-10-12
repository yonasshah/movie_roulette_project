from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.conf import settings
import requests
import random
from .models import UserContent, UserFollow
from django.contrib.auth import get_user_model


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
        is_following = UserFollow.objects.filter(
            follower=request.user, 
            followed=profile_user
        ).exists()

    favorite_list = UserContent.objects.filter(
        user=profile_user,
        list_type=UserContent.ListType.FAVORITE
    ).order_by('-timestamp').values('tmdb_id', 'title', 'poster_path', 'release_year', 'content_type')
    
    # Get the usernames and IDs of the users who follow this profile_user
    followers_list = profile_user.followers.select_related('follower').values('follower__username', 'follower__id')

    # Get the usernames and IDs of the users this profile_user is following
    following_list = profile_user.following.select_related('followed').values('followed__username', 'followed__id')
    
    # Calculate counts for display
    followers_count = followers_list.count()
    following_count = following_list.count()
    
    context = {
        'profile_user': profile_user,
        'is_following': is_following,
        'favorite_list': list(favorite_list),
        'is_owner': request.user == profile_user,
        'settings': settings, # Pass settings for template tags
        
        'followers_list': list(followers_list),
        'following_list': list(following_list),
        'followers_count': followers_count,
        'following_count': following_count,
    }
    
    # The template name must match the one in Step 5
    return render(request, 'roulette/profile.html', context)


# --- 2. TOGGLE FOLLOW API VIEW (Handles POST requests) ---
@login_required
@require_POST
def toggle_follow(request):
    followed_user_id = request.POST.get('user_id') 
    User = get_user_model()
    followed_user = get_object_or_404(User, id=followed_user_id)
    
    if request.user == followed_user:
        return JsonResponse({'success': False, 'error': 'Cannot follow yourself.'}, status=400)

    try:
        follow_instance = UserFollow.objects.get(
            follower=request.user, 
            followed=followed_user
        )
        follow_instance.delete()
        is_following = False
        message = f"Unfollowed {followed_user.username}."
    except UserFollow.DoesNotExist:
        UserFollow.objects.create(
            follower=request.user, 
            followed=followed_user
        )
        is_following = True
        message = f"Now following {followed_user.username}!"
        
    return JsonResponse({'success': True, 'is_following': is_following, 'message': message})

# This is an API view that the JavaScript on your page will call.
# It finds a random movie from TMDb based on the user's filters.
@login_required
def get_random_content(request):
    BASE_URL = "https://api.themoviedb.org/3"
    
    # Get content_type from the frontend request
    content_type = request.GET.get('content_type', 'movie') 

    # Get filter parameters from the frontend request
    genre = request.GET.get('genre', '')
    platform = request.GET.get('with_watch_providers', '')
    # The 'year' filter key changes, so we store the year here and use the dynamic key later
    year = request.GET.get('primary_release_date.gte', '1950')
    mood_genre = request.GET.get('mood_genre', '')

    all_genres = f"{genre},{mood_genre}".strip(',')

    # Map the frontend string to the model's ContentType enum for saving later
    model_content_type = UserContent.ContentType.MOVIE if content_type == 'movie' else UserContent.ContentType.TV

    # Determine the correct API endpoints and parameter based on content_type
    endpoint_type = 'movie' if content_type == 'movie' else 'tv'
    release_date_param = 'primary_release_date.gte' if content_type == 'movie' else 'first_air_date.gte'

    try:
        # Step 1: Find out how many pages of results exist for the user's filters.
        # 1. FIX: The discover_params dictionary MUST be defined before it is used.
        discover_params = {
            "api_key": settings.TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "include_adult": "false",
            "watch_region": "US",
            "with_genres": all_genres,
            "with_watch_providers": platform,
            release_date_param: f"{year}-01-01", # Use dynamic key here
            "vote_count.gte": 100 # Only get content with a decent number of votes
        }
        
        discover_res = requests.get(f"{BASE_URL}/discover/{endpoint_type}", params=discover_params)
        discover_res.raise_for_status() # Raises an error if the request failed
        total_pages = discover_res.json().get('total_pages', 1)
        
        # Step 2: Pick a random page number.
        # TMDb's API has a limit of 500 pages.
        random_page = random.randint(1, min(total_pages, 500))
        
        # Step 3: Fetch all movies/shows from that random page.
        discover_params['page'] = random_page
        # Use the dynamic endpoint again
        movies_res = requests.get(f"{BASE_URL}/discover/{endpoint_type}", params=discover_params) 
        movies_res.raise_for_status()
        results = movies_res.json().get('results', [])

        if not results:
            return JsonResponse({'error': 'No content found with the selected filters.'}, status=404)

        # Step 4: Pick a random content item from that page's results.
        random_content_base = random.choice(results)
        content_id = random_content_base['id']

        # Step 5: Get the detailed information for that one specific content item.
        detail_params = {
            "api_key": settings.TMDB_API_KEY,
            "append_to_response": "videos,watch/providers" # Get trailer and streaming info
        }
        # Use the dynamic detail endpoint: /movie/{id} or /tv/{id}
        detail_res = requests.get(f"{BASE_URL}/{endpoint_type}/{content_id}", params=detail_params)
        detail_res.raise_for_status()
        content_details = detail_res.json()
        
        # ADD content_type to the response for the frontend
        content_details['content_type'] = content_type

        # Step 6: Add this content to the user's viewing history.
        # TMDb uses 'title'/'release_date' for movies and 'name'/'first_air_date' for TV shows.
        title_key = 'title' if content_type == 'movie' else 'name'
        date_key = 'release_date' if content_type == 'movie' else 'first_air_date'

        UserContent.objects.update_or_create(
            user=request.user,
            tmdb_id=content_id,
            list_type=UserContent.ListType.HISTORY,
            defaults={
                'title': content_details.get(title_key, 'N/A'), # Use dynamic key
                'poster_path': content_details.get('poster_path', ''),
                'release_year': content_details.get(date_key, '----')[:4], # Use dynamic key
                'content_type': model_content_type, # Save the content type
            }
        )

        # Step 7: Send the detailed movie data back to the frontend.
        return JsonResponse(content_details)

    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f"API request failed: {e}"}, status=500)

# This view fetches the user's saved lists from the database.
@login_required
def get_user_lists(request):
    favorites = UserContent.objects.filter(user=request.user, list_type=UserContent.ListType.FAVORITE)
    history = UserContent.objects.filter(user=request.user, list_type=UserContent.ListType.HISTORY)
    
    current_content_id = request.GET.get('content_id')
    is_favorite = False
    if current_content_id:
        is_favorite = favorites.filter(content_id=current_content_id).exists()

    return JsonResponse({
        'favorites': list(favorites.values('id', 'title', 'poster_path', 'release_year')),
        'history': list(history.values('id', 'title', 'poster_path', 'release_year')),
        'is_favorite': is_favorite,
    })

# This view handles adding or removing a movie from the user's favorites.
@login_required
@require_POST
def toggle_favorite(request):
    content_id = request.POST.get('content_id')
    title = request.POST.get('title')
    poster_path = request.POST.get('poster_path')
    release_year = request.POST.get('release_year')

    try:
        favorite, created = UserContent.objects.get_or_create(
            user=request.user,
            content_id=content_id,
            list_type=UserContent.ListType.FAVORITE,
            defaults={'title': title, 'poster_path': poster_path, 'release_year': release_year}
        )
        if not created:
            favorite.delete()
            is_favorite = False
        else:
            is_favorite = True
        return JsonResponse({'success': True, 'is_favorite': is_favorite})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})