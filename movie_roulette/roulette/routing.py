# movie_roulette/roulette/routing.py
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/feed/$', consumers.FeedConsumer.as_asgi()), # URL for feed updates
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()), # URL for notifications
    # Add other WebSocket routes here if needed
]