# roulette/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import SharedListPost, Notification, Comment, Like, UserContent
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string


# --- Receiver for SharedListPost ---
@receiver(post_save, sender=SharedListPost)
def broadcast_new_feed_item(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group_name = 'feed_updates'
        item_html = None # Initialize item_html

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

        
@receiver(post_save, sender=UserContent)
def broadcast_new_usercontent_item(sender, instance, created, **kwargs):
    # Only broadcast for NEW items, and EXCLUDE history items
    if created and instance.list_type != UserContent.ListType.HISTORY:
        channel_layer = get_channel_layer()
        group_name = 'feed_updates'

        # Get ContentType ID for UserContent
        try:
            usercontent_ct = ContentType.objects.get_for_model(UserContent)
            ctype_id = usercontent_ct.id
        except ContentType.DoesNotExist:
            print(f"Error: ContentType for UserContent not found.")
            return # Cannot proceed

        # Prepare data to send via WebSocket
        message_data = {
            'type': 'list_item', # Indicate the type of item
            'user_id': instance.user.id,
            'username': instance.user.username,
            'profile_image_url': instance.user.profile.image.url,
            'list_type': instance.list_type, # e.g., 'FAVORITE', 'WATCHLIST', 'CUSTOM'
            'content_type': instance.content_type, # 'MOVIE' or 'TV'
            'tmdb_id': instance.tmdb_id,
            'title': instance.title,
            'poster_path': instance.poster_path,
            'release_year': instance.release_year,
            'timestamp_iso': instance.timestamp.isoformat(),
            # Include IDs needed for like/comment functionality on the UserContent item itself
            'ctype_id': ctype_id,
            'obj_id': instance.id,
            # Include custom list details if applicable
            'custom_list_id': instance.custom_list.id if instance.list_type == UserContent.ListType.CUSTOM and instance.custom_list else None,
            'custom_list_name': instance.custom_list.name if instance.list_type == UserContent.ListType.CUSTOM and instance.custom_list else None,
        }

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'feed.new_item', # Reuse the same consumer method type
                'data': message_data # Send JSON data
            }
        )


# --- Receiver for Notification ---
@receiver(post_save, sender=Notification)
def send_notification_update(sender, instance, created, **kwargs):
    # Only send for new, unread notifications where recipient isn't the actor (avoid self-notify)
    if created and not instance.read and instance.recipient != instance.actor:
        channel_layer = get_channel_layer()
        # Create a user-specific group name (e.g., "notifications_user_5")
        user_specific_group = f'notifications_user_{instance.recipient.id}'

        print(f"Signal: Sending notification update for user {instance.recipient.id} to group {user_specific_group}")

        unread_count = Notification.objects.filter(recipient=instance.recipient, read=False).count()

        actor_name = instance.actor.username if instance.actor else 'System'
        message_text = f"New notification: {actor_name} {instance.verb}."

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
        print(f"Signal: Sent update to group {user_specific_group}")


# --- Receiver for Comment ---
@receiver(post_save, sender=Comment)
def send_new_comment(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group_name = 'feed_updates'

        try:
            comment_html = render_to_string('roulette/_comment.html', {'comment': instance})
        except Exception as e:
            print(f"Error rendering comment HTML in signal: {e}")
            comment_html = "<p>Error loading comment.</p>"

        print(f"Signal: Sending new comment for {instance.content_type_id}:{instance.object_id} to group {group_name}")

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'feed.new_comment', # Method name in FeedConsumer
                'data': {
                    'ctype_id': instance.content_type_id,
                    'obj_id': instance.object_id,
                    'comment_html': comment_html,
                    'commenter_id': instance.user.id
                }
            }
        )
        print(f"Signal: Sent new comment update to group {group_name}")


# --- Function to send like update (used by post_save and post_delete) ---
def send_like_update(instance):
    channel_layer = get_channel_layer()
    group_name = 'feed_updates'

    like_count = Like.objects.filter(
        content_type_id=instance.content_type_id,
        object_id=instance.object_id
    ).count()

    print(f"Signal: Sending like update for {instance.content_type_id}:{instance.object_id}, new count: {like_count}")

    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'feed.like_update', # Method name in FeedConsumer
            'data': {
                'ctype_id': instance.content_type_id,
                'obj_id': instance.object_id,
                'like_count': like_count,
            }
        }
    )
    print(f"Signal: Sent like update to group {group_name}")


# --- Receivers for Like model ---
@receiver(post_save, sender=Like)
def send_like_update_on_save(sender, instance, created, **kwargs):
    if created:
        send_like_update(instance)

@receiver(post_delete, sender=Like)
def send_like_update_on_delete(sender, instance, **kwargs):
    send_like_update(instance)