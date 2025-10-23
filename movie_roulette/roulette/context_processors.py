# movie_roulette/roulette/context_processors.py

from .models import Notification

def unread_notifications_count(request):
    """
    Adds the count of unread notifications to the template context
    for the logged-in user.
    """
    if request.user.is_authenticated:
        count = Notification.objects.filter(recipient=request.user, read=False).count()
        return {'unread_notifications_count': count}
    return {'unread_notifications_count': 0} # Return 0 if user is not logged in