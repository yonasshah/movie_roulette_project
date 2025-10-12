from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    # Add this line for the new users app
    path('accounts/', include('users.urls')),
    # Keep the line for your main movie roulette app
    path('', include('roulette.urls')),
]
