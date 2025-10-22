from django.urls import path
from . import views

app_name = 'roulette'

urlpatterns = [
    path('', views.roulette_view, name='roulette_view'),
    path('discover/', views.discover_view, name='discover'),
    path('api/get-random-content/', views.get_random_content, name='get_random_content'),
    path('api/get-user-lists/', views.get_user_lists, name='get_user_lists'),
    path('api/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('api/toggle-follow/', views.toggle_follow, name='toggle_follow'),
    path('user/<str:username>/', views.user_profile_view, name='user_profile'),
    path('search/', views.search_view, name='search_results'),
    path('content/<str:content_type>/<int:tmdb_id>/', views.content_detail_view, name='content_detail'),
]