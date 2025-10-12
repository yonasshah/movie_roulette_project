from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.conf import settings
import requests
import random
from .models import UserMovie

# This view is responsible for showing the main page of your app.
@login_required
def roulette_view(request):
    return render(request, 'roulette/roulette.html')


# This is an API view that the JavaScript on your page will call.
# It finds a random movie from TMDb based on the user's filters.
@login_required
def get_random_movie(request):
    BASE_URL = "https://api.themoviedb.org/3"
    
    # Get filter parameters from the frontend request
    genre = request.GET.get('genre', '')
    platform = request.GET.get('with_watch_providers', '')
    year = request.GET.get('primary_release_date.gte', '1950')
    mood_genre = request.GET.get('mood_genre', '')

    all_genres = f"{genre},{mood_genre}".strip(',')

    try:
        # Step 1: Find out how many pages of results exist for the user's filters.
        discover_params = {
            "api_key": settings.TMDB_API_KEY,
            "language": "en-US",
            "sort_by": "popularity.desc",
            "include_adult": "false",
            "watch_region": "US",
            "with_genres": all_genres,
            "with_watch_providers": platform,
            "primary_release_date.gte": f"{year}-01-01",
            "vote_count.gte": 100 # Only get movies with a decent number of votes
        }
        discover_res = requests.get(f"{BASE_URL}/discover/movie", params=discover_params)
        discover_res.raise_for_status() # Raises an error if the request failed
        total_pages = discover_res.json().get('total_pages', 1)
        
        # Step 2: Pick a random page number.
        # TMDb's API has a limit of 500 pages.
        random_page = random.randint(1, min(total_pages, 500))
        
        # Step 3: Fetch all movies from that random page.
        discover_params['page'] = random_page
        movies_res = requests.get(f"{BASE_URL}/discover/movie", params=discover_params)
        movies_res.raise_for_status()
        results = movies_res.json().get('results', [])

        if not results:
            return JsonResponse({'error': 'No movies found with the selected filters.'}, status=404)

        # Step 4: Pick a random movie from that page's results.
        random_movie_base = random.choice(results)
        movie_id = random_movie_base['id']

        # Step 5: Get the detailed information for that one specific movie.
        detail_params = {
            "api_key": settings.TMDB_API_KEY,
            "append_to_response": "videos,watch/providers" # Get trailer and streaming info
        }
        detail_res = requests.get(f"{BASE_URL}/movie/{movie_id}", params=detail_params)
        detail_res.raise_for_status()
        movie_details = detail_res.json()
        
        # Step 6: Add this movie to the user's viewing history.
        UserMovie.objects.update_or_create(
            user=request.user,
            movie_id=movie_id,
            list_type=UserMovie.ListType.HISTORY,
            defaults={
                'title': movie_details.get('title', 'N/A'),
                'poster_path': movie_details.get('poster_path', ''),
                'release_year': movie_details.get('release_date', '----')[:4],
            }
        )

        # Step 7: Send the detailed movie data back to the frontend.
        return JsonResponse(movie_details)

    except requests.exceptions.RequestException as e:
        return JsonResponse({'error': f"API request failed: {e}"}, status=500)

# This view fetches the user's saved lists from the database.
@login_required
def get_user_lists(request):
    favorites = UserMovie.objects.filter(user=request.user, list_type=UserMovie.ListType.FAVORITE)
    history = UserMovie.objects.filter(user=request.user, list_type=UserMovie.ListType.HISTORY)
    
    current_movie_id = request.GET.get('movie_id')
    is_favorite = False
    if current_movie_id:
        is_favorite = favorites.filter(movie_id=current_movie_id).exists()

    return JsonResponse({
        'favorites': list(favorites.values('id', 'title', 'poster_path', 'release_year')),
        'history': list(history.values('id', 'title', 'poster_path', 'release_year')),
        'is_favorite': is_favorite,
    })

# This view handles adding or removing a movie from the user's favorites.
@login_required
@require_POST
def toggle_favorite(request):
    movie_id = request.POST.get('movie_id')
    title = request.POST.get('title')
    poster_path = request.POST.get('poster_path')
    release_year = request.POST.get('release_year')

    try:
        favorite, created = UserMovie.objects.get_or_create(
            user=request.user,
            movie_id=movie_id,
            list_type=UserMovie.ListType.FAVORITE,
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