from django.urls import path
from . import views

# This is the URL namespace for this app
app_name = 'roulette'

urlpatterns = [
    # Main page for the app (e.g., /)
    path('', views.roulette_view, name='roulette_view'),

    # API endpoints that the JavaScript will call
    path('api/get-random-movie/', views.get_random_movie, name='get_random_movie'),
    path('api/get-user-lists/', views.get_user_lists, name='get_user_lists'),
    path('api/toggle-favorite/', views.toggle_favorite, name='toggle_favorite'),
]