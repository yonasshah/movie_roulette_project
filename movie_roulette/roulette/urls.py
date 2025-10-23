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
    path('api/toggle-watchlist/', views.toggle_watchlist, name='toggle_watchlist'),
    path('user/<str:username>/', views.user_profile_view, name='user_profile'),
    path('search/', views.search_view, name='search_results'),
    path('content/<str:content_type>/<int:tmdb_id>/', views.content_detail_view, name='content_detail'),
    path('lists/', views.list_all_lists_view, name='list_all'),        # Page to view/create lists
    path('lists/create/', views.create_list_view, name='list_create'),  # Handles list creation form POST
    path('list/<int:list_id>/', views.list_detail_view, name='list_detail'), # View items in a specific list
    path('list/<int:list_id>/delete/', views.delete_list_view, name='list_delete'), # Handles list deletion
    path('list/add-item/', views.add_to_custom_list_view, name='list_add_item'), # API endpoint to add item
    path('list/remove-item/', views.remove_from_custom_list_view, name='list_remove_item'), # API endpoint to remove item
    path('content/<str:content_type>/<int:tmdb_id>/review/', views.add_review, name='add_review'),
    path('review/<int:review_id>/delete/', views.delete_review, name='delete_review'),
    path('feed/', views.feed_view, name='feed'),
    path('comment/add/', views.add_comment_view, name='add_comment'),
    path('comment/<int:comment_id>/delete/', views.delete_comment_view, name='delete_comment'),
    path('like/toggle/', views.toggle_like_view, name='toggle_like'),
    path('notifications/', views.notifications_view, name='notifications'),
]