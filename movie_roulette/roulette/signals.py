# roulette/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
# Remove render_to_string import if not used elsewhere
# from django.template.loader import render_to_string
from .models import SharedListPost
from django.contrib.contenttypes.models import ContentType # Import ContentType

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

# --- Add receivers for other models (Review, Comment, Like) here later if needed ---