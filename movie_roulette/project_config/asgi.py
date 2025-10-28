# project_config/asgi.py
import os
from django.core.asgi import get_asgi_application

# Set DJANGO_SETTINGS_MODULE first (important!)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_config.settings')

# Initialize Django ASGI application BEFORE importing routing/consumers
# This ensures Django apps are loaded.
django_asgi_app = get_asgi_application()

# Now import Channels and your routing AFTER Django setup
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack # If you need user auth in websockets
import roulette.routing # Import your app's routing

application = ProtocolTypeRouter({
    "http": django_asgi_app, # Use the initialized app for HTTP
    "websocket": AuthMiddlewareStack( # Handles WebSockets, wraps auth
        URLRouter(
            roulette.routing.websocket_urlpatterns # Point to your app's WebSocket URLs
        )
    ),
})