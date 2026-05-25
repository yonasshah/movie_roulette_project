# roulette/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async # Import sync_to_async
from .models import Notification # Import Notification model
import logging


logger = logging.getLogger(__name__)

# --- FeedConsumer ---
class FeedConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        self.group_name = 'feed_updates'

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        logger.debug("Feed websocket connected.")

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            logger.debug("Feed websocket disconnecting.")
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            logger.debug("Feed websocket disconnected.")

    async def feed_new_item(self, event):
        message_data = event['data']
        item_type = message_data.get('type')

        logger.debug("Feed websocket new item event received. item_type=%s", item_type)

        try:
            await self.send(text_data=json.dumps({
                'type': 'new_item',
                'data': message_data,
            }))
        except Exception:
            logger.exception("Failed to send feed new item websocket event. item_type=%s", item_type)
            return

        logger.debug("Feed websocket new item event sent. item_type=%s", item_type)

    async def feed_removed_item(self, event):
        message_data = event['data']

        logger.debug("Feed websocket removed item event received.")

        await self.send(text_data=json.dumps({
            'type': 'removed_item',
            'data': message_data,
        }))

        logger.debug("Feed websocket removed item event sent.")

    async def feed_vote_update(self, event):
        message_data = event['data']

        logger.debug("Feed websocket vote update event received. data=%s", message_data)

        await self.send(text_data=json.dumps({
            'type': 'vote_update',
            'data': message_data,
        }))

        logger.debug("Feed websocket vote update event sent.")

    async def feed_deleted_comment(self, event):
        message_data = event['data']

        logger.debug("Feed websocket deleted comment event received. data=%s", message_data)

        await self.send(text_data=json.dumps({
            'type': 'deleted_comment',
            'data': message_data,
        }))

        logger.debug("Feed websocket deleted comment event sent.")

    async def feed_new_comment(self, event):
        message_data = event['data']

        logger.debug("Feed websocket new comment event received. data=%s", message_data)

        await self.send(text_data=json.dumps({
            'type': 'new_comment',
            'data': message_data,
        }))

        logger.debug("Feed websocket new comment event sent.")

    async def feed_like_update(self, event):
        message_data = event['data']

        logger.debug("Feed websocket like update event received. data=%s", message_data)

        await self.send(text_data=json.dumps({
            'type': 'like_update',
            'data': message_data,
        }))

        logger.debug("Feed websocket like update event sent.")


# --- NotificationConsumer ---
class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close() # Reject unauthenticated users
            logger.debug("Notification websocket rejected unauthenticated connection.")
            return

        # Each user joins a group named after their user ID
        self.group_name = f'notifications_user_{self.user.id}'

        # Join user-specific group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        logger.debug("Notification websocket connected for authenticated user.")

        # Optionally send current count upon connection
        current_count = await self.get_unread_count()
        await self.send(text_data=json.dumps({
            'type': 'notification_count_update',
            'unread_count': current_count
        }))


    async def disconnect(self, close_code):
        # Ensure user is authenticated before trying to access self.user.id
        if hasattr(self, 'user') and self.user.is_authenticated and hasattr(self, 'group_name'):
            logger.debug("Notification websocket disconnecting for authenticated user.")
            # Leave user-specific group
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            logger.debug("Notification websocket disconnected for authenticated user.")
        else:
            logger.warning("Notification websocket disconnected before full authentication/setup.")


    # Receive message from user-specific group (triggered by signal)
    async def user_notification(self, event):
        message_data = event['data']
        logger.debug("Notification websocket event received.")

        # Send message data (e.g., new count) to WebSocket client (browser)
        await self.send(text_data=json.dumps({
            'type': 'notification_count_update', # Tell JS this is just a count update
            'unread_count': message_data.get('unread_count', 0),
            'new_message': message_data.get('message', None) # Optionally send message text for popups
        }))
        logger.debug("Notification websocket count update sent.")

    # Helper to get count asynchronously
    @sync_to_async
    def get_unread_count(self):
         # Check authentication within the async helper too
         if hasattr(self, 'user') and self.user.is_authenticated:
            return Notification.objects.filter(recipient=self.user, read=False).count()
         return 0