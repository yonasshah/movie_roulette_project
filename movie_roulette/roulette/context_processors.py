from .models import Notification

def unread_notifications_count(request):
    if request.user.is_authenticated:
        notifications = Notification.objects.filter(
            recipient=request.user
        ).select_related(
            "actor",
            "actor__profile",
            "target_content_type",
            "action_object_content_type",
        )[:8]

        count = Notification.objects.filter(
            recipient=request.user,
            read=False
        ).count()

        return {
            "unread_notifications_count": count,
            "recent_notifications": notifications,
        }

    return {
        "unread_notifications_count": 0,
        "recent_notifications": [],
    }