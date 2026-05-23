# roulette/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import SharedListPost, Notification, Comment, Like, UserContent, Vote
from django.contrib.contenttypes.models import ContentType
from django.template.loader import render_to_string



def _get_notification_owner(obj):
    """
    Returns the user who owns a feed/comment target, if available.
    """
    if hasattr(obj, "user"):
        return obj.user
    return None


def _get_target_title(obj):
    """
    Gets a human-friendly title/name for notification text.
    """
    if hasattr(obj, "title") and obj.title:
        return obj.title

    if hasattr(obj, "name") and obj.name:
        return obj.name

    if hasattr(obj, "list") and obj.list:
        return obj.list.name

    return "your post"


def _get_list_context(obj):
    """
    Adds list context like 'in Spring List' when available.
    """
    if hasattr(obj, "custom_list") and obj.custom_list:
        return f" in {obj.custom_list.name}"

    if hasattr(obj, "list") and obj.list:
        return f" in {obj.list.name}"

    return ""


def _create_notification_once(recipient, actor, verb, target):
    """
    Prevents duplicate notifications for repeatable actions like upvotes/follows.
    Comments are naturally unique, but this is useful for votes.
    """
    if not recipient or not actor or recipient == actor or not target:
        return None

    target_ct = ContentType.objects.get_for_model(target.__class__)

    notification, created = Notification.objects.get_or_create(
        recipient=recipient,
        actor=actor,
        verb=verb,
        target_content_type=target_ct,
        target_object_id=target.id,
    )

    return notification


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
            print("Error: ContentType for SharedListPost not found.")
            return

        # Add temporary attributes so the feed card template can render this
        # SharedListPost object like a normal feed item.
        instance.type = 'share'
        instance.ctype_id = ctype_id
        instance.obj_id = instance.id
        instance.fetched_user_vote = 0
        instance.fetched_up_count = 0
        instance.fetched_down_count = 0
        instance.fetched_comment_count = 0
        instance.fetched_comments = []

        item_html = render_to_string(
            'roulette/partials/_feed_card.html',
            {
                'item': instance,
                'user': instance.user,
                'request': None,
            }
        )

        # Prepare data to send via WebSocket
        message_data = {
            'type': 'share',
            'post_id': instance.id,
            'user_id': instance.user.id,
            'username': instance.user.username,
            'profile_image_url': instance.user.profile.image.url,
            'list_id': instance.list.id,
            'list_name': instance.list.name,
            'list_url': instance.list.get_absolute_url(),
            'list_description': instance.list.description,
            'share_message': instance.message,
            'timestamp_iso': instance.timestamp.isoformat(),
            'ctype_id': ctype_id,
            'obj_id': instance.id,
            'html': item_html,
        }

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'feed.new_item',
                'data': message_data
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
        
        instance.type = 'list_item'
        instance.ctype_id = ctype_id
        instance.obj_id = instance.id
        instance.fetched_user_vote = 0
        instance.fetched_up_count = 0
        instance.fetched_down_count = 0
        instance.fetched_comment_count = 0
        instance.fetched_comments = []

        item_html = render_to_string(
            'roulette/partials/_feed_card.html',
            {
                'item': instance,
                'user': instance.user,
                'request': None,
            }
        )

        # Prepare data to send via WebSocket
        message_data = {
            'type': 'list_item',
            'user_id': instance.user.id,
            'username': instance.user.username,
            'profile_image_url': instance.user.profile.image.url,
            'list_type': instance.list_type,
            'content_type': instance.content_type,
            'tmdb_id': instance.tmdb_id,
            'title': instance.title,
            'poster_path': instance.poster_path,
            'release_year': instance.release_year,
            'timestamp_iso': instance.timestamp.isoformat(),
            'ctype_id': ctype_id,
            'obj_id': instance.id,
            'html': item_html,
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

@receiver(post_delete, sender=UserContent)
def broadcast_removed_usercontent_item(sender, instance, **kwargs):
    # Only remove feed cards for list items that appear in the feed.
    # History items are not shown in the feed.
    if instance.list_type == UserContent.ListType.HISTORY:
        return

    channel_layer = get_channel_layer()
    group_name = 'feed_updates'

    try:
        usercontent_ct = ContentType.objects.get_for_model(UserContent)
        ctype_id = usercontent_ct.id
    except ContentType.DoesNotExist:
        print("Error: ContentType for UserContent not found.")
        return

    message_data = {
        'type': 'list_item',
        'user_id': instance.user.id,
        'ctype_id': ctype_id,
        'obj_id': instance.id,
        'tmdb_id': instance.tmdb_id,
        'content_type': instance.content_type,
        'list_type': instance.list_type,
    }

    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'feed.removed_item',
            'data': message_data
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
        message_text = f"@{actor_name} {instance.verb}"

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
    if not created:
        return

    # 1. Try notification, but do not let notification errors break live comments.
    try:
        if instance.parent:
            recipient = instance.parent.user
            verb = "replied_to_comment"
        else:
            recipient = _get_notification_owner(instance.content_object)
            verb = "commented_on_post"

        if recipient and recipient != instance.user:
            Notification.objects.create(
                recipient=recipient,
                actor=instance.user,
                verb=verb,
                target_content_type=instance.content_type,
                target_object_id=instance.object_id,
                action_object_content_type=ContentType.objects.get_for_model(Comment),
                action_object_object_id=instance.id,
            )
    except Exception as e:
        print(f"Error creating comment notification: {e}")

    # 2. Always broadcast the live comment.
    channel_layer = get_channel_layer()
    group_name = "feed_updates"

    try:
        comment_html = render_to_string(
            "roulette/_comment.html",
            {
                "comment": instance,
                "request": None,
            }
        )
    except Exception as e:
        print(f"Error rendering comment HTML in signal: {e}")
        comment_html = "<p>Error loading comment.</p>"

    print(f"Signal: Sending new comment for {instance.content_type_id}:{instance.object_id} to group {group_name}")

    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            "type": "feed.new_comment",
            "data": {
                "ctype_id": instance.content_type_id,
                "obj_id": instance.object_id,
                "comment_html": comment_html,
                "commenter_id": instance.user.id,
            },
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
    
def send_vote_update(instance):
    channel_layer = get_channel_layer()
    group_name = 'feed_updates'

    comment_ct = ContentType.objects.get_for_model(Comment)
    is_comment_vote = instance.content_type_id == comment_ct.id

    up_count = Vote.objects.filter(
        content_type_id=instance.content_type_id,
        object_id=instance.object_id,
        vote_type=1
    ).count()

    down_count = Vote.objects.filter(
        content_type_id=instance.content_type_id,
        object_id=instance.object_id,
        vote_type=-1
    ).count()

    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'feed.vote_update',
            'data': {
                'ctype_id': instance.content_type_id,
                'obj_id': instance.object_id,
                'up_count': up_count,
                'down_count': down_count,
                'is_comment_vote': is_comment_vote,
            }
        }
    )


@receiver(post_save, sender=Vote)
def send_vote_update_on_save(sender, instance, created, **kwargs):
    send_vote_update(instance)

    # Only notify for new upvotes, not downvotes.
    if not created or instance.vote_type != 1:
        return

    target = instance.content_object
    recipient = _get_notification_owner(target)

    if not recipient or recipient == instance.user:
        return

    title = _get_target_title(target)
    list_context = _get_list_context(target)

    if isinstance(target, Comment):
        verb = "upvoted_comment"
    else:
        verb = "upvoted_post"

    _create_notification_once(
        recipient=recipient,
        actor=instance.user,
        verb=verb,
        target=target,
    )


@receiver(post_delete, sender=Vote)
def send_vote_update_on_delete(sender, instance, **kwargs):
    send_vote_update(instance)

    # If an upvote is removed, remove the matching notification.
    if instance.vote_type != 1:
        return

    target = instance.content_object
    recipient = _get_notification_owner(target)

    if not recipient or recipient == instance.user:
        return

    target_ct = ContentType.objects.get_for_model(target.__class__)
    title = _get_target_title(target)
    list_context = _get_list_context(target)

    if isinstance(target, Comment):
        verb = "upvoted_comment"
    else:
        verb = "upvoted_post"

    Notification.objects.filter(
        recipient=recipient,
        actor=instance.user,
        verb=verb,
        target_content_type=target_ct,
        target_object_id=target.id,
    ).delete()
    
@receiver(post_delete, sender=Comment)
def send_deleted_comment(sender, instance, **kwargs):
    channel_layer = get_channel_layer()
    group_name = 'feed_updates'

    async_to_sync(channel_layer.group_send)(
        group_name,
        {
            'type': 'feed.deleted_comment',
            'data': {
                'comment_id': instance.id,
                'ctype_id': instance.content_type_id,
                'obj_id': instance.object_id,
            }
        }
    )