from django.urls import path
from . import views

app_name = 'roulette'

urlpatterns = [
    # Core & Discovery
    path('', views.roulette_view, name='roulette_view'),
    path('discover/', views.discover_view, name='discover'),
    path('search/', views.search_view, name='search_results'),
    path("ai/mood-filters/", views.generate_mood_filters_view, name="generate_mood_filters"),
    path("ai/explain-pick/", views.explain_recommendation_view, name="explain_recommendation"),

    # Content Detail & Reviews
    path('content/<str:content_type>/<int:tmdb_id>/', views.content_detail_view, name='content_detail'),
    path('content/<str:content_type>/<int:tmdb_id>/review/', views.add_review, name='add_review'),
    path('review/<int:review_id>/delete/', views.delete_review, name='delete_review'),

    # User Profile & Following
    path('user/<str:username>/', views.user_profile_view, name='user_profile'),
    path('api/toggle-follow/', views.toggle_follow, name='toggle_follow'), # Keep as API if using AJAX

    # Built-in Lists (Favorites, Watchlist, History - APIs)
    path('api/get-random-content/', views.get_random_content, name='get_random_content'), # Includes history add
    path('api/get-user-lists/', views.get_user_lists, name='get_user_lists'), # Gets all list types for display
    path('api/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('api/toggle-watchlist/', views.toggle_watchlist, name='toggle_watchlist'),

    # Custom Lists (Pages & APIs)
    path('lists/', views.list_all_lists_view, name='list_all'),        # Page to view/create lists
    path('lists/create/', views.create_list_view, name='list_create'),  # Handles list creation form POST (AJAX)
    path('list/<int:list_id>/', views.list_detail_view, name='list_detail'), # View items in a specific list (Handles public/private)
    path('list/<int:list_id>/delete/', views.delete_list_view, name='list_delete'), # Handles list deletion (AJAX or form POST)
    path('list/add-item/', views.add_to_custom_list_view, name='list_add_item'), # API endpoint to add item (AJAX)
    path('list/remove-item/', views.remove_from_custom_list_view, name='list_remove_item'), # API endpoint to remove item (AJAX)

    # --- NEW: Custom List Sharing ---
    path('list/<int:list_id>/toggle-public/', views.toggle_list_public_view, name='list_toggle_public'), # API for public toggle (AJAX)
    path('list/<int:list_id>/share/', views.share_list_to_feed_view, name='list_share_feed'), # Handles share form POST

    # Feed, Comments, Likes, Notifications
    path('feed/', views.feed_view, name='feed'),
    path('comment/add/', views.add_comment_view, name='add_comment'), # Handles comment form POST (AJAX or form POST)
    path('comment/<int:comment_id>/delete/', views.delete_comment_view, name='delete_comment'), # Handles comment deletion (AJAX or form POST)
    path('like/toggle/', views.toggle_like_view, name='toggle_like'), # API for liking (AJAX)
    path('notifications/', views.notifications_view, name='notifications'),
    path('vote/toggle/', views.toggle_vote_view, name='toggle_vote'),
    path('comment/<int:comment_id>/edit/', views.edit_comment_view, name='edit_comment'),
]