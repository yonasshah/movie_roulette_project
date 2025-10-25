# project_config/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack # If you need user auth in websockets
import roulette.routing # Import your app's routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_config.settings')

# application = get_asgi_application() # Keep the original for HTTP

application = ProtocolTypeRouter({
    "http": get_asgi_application(), # Handles standard HTTP requests
    "websocket": AuthMiddlewareStack( # Handles WebSockets, wraps auth
        URLRouter(
            roulette.routing.websocket_urlpatterns # Point to your app's WebSocket URLs
        )
    ),
})