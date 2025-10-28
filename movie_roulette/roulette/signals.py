# roulette/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
# Import Notification model
from .models import SharedListPost, Notification # <<< ADDED Notification
from django.contrib.contenttypes.models import ContentType # Import ContentType

# --- Receiver for SharedListPost ---
@receiver(post_save, sender=SharedListPost)
def broadcast_new_feed_item(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group_name = 'feed_updates'

        # Get ContentType ID for SharedListPost
        try:
            shared_list_post_ct = ContentType.objects.get_for_model(SharedListPost)
            ctype_id = shared_list_post_ct.id
        except ContentType.DoesNotExist:
            print(f"Error: ContentType for SharedListPost not found.")
            return # Cannot proceed without ContentType

        # Prepare data to send via WebSocket
        message_data = {
            'type': 'share', # Indicate the type of item
            'post_id': instance.id,
            'user_id': instance.user.id,
            'username': instance.user.username,
            'profile_image_url': instance.user.profile.image.url,
            'list_id': instance.list.id,
            'list_name': instance.list.name,
            'list_url': instance.list.get_absolute_url(),
            'list_description': instance.list.description, # Send description
            'share_message': instance.message,
            'timestamp_iso': instance.timestamp.isoformat(), # Send ISO format for JS parsing
            # Include IDs needed for like/comment functionality on the SharedListPost itself
            'ctype_id': ctype_id,
            'obj_id': instance.id,
        }

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'feed.new_item', # Use a different type for the consumer method
                'data': message_data # Send JSON data
            }
        )

# --- NEW: Receiver for Notification ---
@receiver(post_save, sender=Notification)
def send_notification_update(sender, instance, created, **kwargs):
    # Only send for new, unread notifications where recipient isn't the actor (avoid self-notify)
    if created and not instance.read and instance.recipient != instance.actor:
        channel_layer = get_channel_layer()
        # Create a user-specific group name (e.g., "notifications_user_5")
        user_specific_group = f'notifications_user_{instance.recipient.id}'

        print(f"Signal: Sending notification update for user {instance.recipient.id} to group {user_specific_group}") # Logging

        # Send a simple message indicating a new notification and the current unread count
        # Calculate count within the async context for accuracy
        unread_count = Notification.objects.filter(recipient=instance.recipient, read=False).count()

        # Construct a basic message text
        actor_name = instance.actor.username if instance.actor else 'System'
        message_text = f"New notification: {actor_name} {instance.verb}."
        # You could enhance this message based on notification.target/action_object later

        async_to_sync(channel_layer.group_send)(
            user_specific_group,
            {
                'type': 'user.notification', # Method name in the NotificationConsumer
                'data': {
                    'unread_count': unread_count,
                    'message': message_text
                }
            }
        )
        print(f"Signal: Sent update to group {user_specific_group}") # Logging

# --- Add receivers for other models (Comment, Like) here later if needed ---