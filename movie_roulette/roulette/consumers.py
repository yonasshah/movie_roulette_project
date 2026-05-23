# roulette/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async # Import sync_to_async
from .models import Notification # Import Notification model

# --- FeedConsumer ---
# --- FeedConsumer ---
class FeedConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = 'feed_updates'

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        print(f"FeedConsumer: WebSocket connected and added to group {self.group_name}")

    async def disconnect(self, close_code):
        print(f"FeedConsumer: WebSocket disconnecting from group {self.group_name}...")

        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

        print("FeedConsumer: WebSocket disconnected.")

    async def feed_new_item(self, event):
        message_data = event['data']
        item_type = message_data.get('type')

        print(f"FeedConsumer: Received feed_new_item of type '{item_type}': {message_data}")

        await self.send(text_data=json.dumps({
            'type': 'new_item',
            'data': message_data,
        }))

        print(f"FeedConsumer: Sent new_item message (type: {item_type}) to client.")
        
    

    async def feed_removed_item(self, event):
        message_data = event['data']

        print(f"FeedConsumer: Received feed_removed_item: {message_data}")

        await self.send(text_data=json.dumps({
            'type': 'removed_item',
            'data': message_data,
        }))

        print("FeedConsumer: Sent removed_item message to client.")
        
    async def feed_vote_update(self, event):
        message_data = event['data']

        print(f"FeedConsumer: Received feed_vote_update: {message_data}")

        await self.send(text_data=json.dumps({
            'type': 'vote_update',
            'data': message_data,
        }))

        print("FeedConsumer: Sent vote_update message to client.")


    async def feed_deleted_comment(self, event):
        message_data = event['data']

        print(f"FeedConsumer: Received feed_deleted_comment: {message_data}")

        await self.send(text_data=json.dumps({
            'type': 'deleted_comment',
            'data': message_data,
        }))

        print("FeedConsumer: Sent deleted_comment message to client.")

    async def feed_new_comment(self, event):
        message_data = event['data']

        print(f"FeedConsumer: Received feed_new_comment: {message_data}")

        await self.send(text_data=json.dumps({
            'type': 'new_comment',
            'data': message_data,
        }))

        print("FeedConsumer: Sent new_comment message to client.")

    async def feed_like_update(self, event):
        message_data = event['data']

        print(f"FeedConsumer: Received feed_like_update: {message_data}")

        await self.send(text_data=json.dumps({
            'type': 'like_update',
            'data': message_data,
        }))

        print("FeedConsumer: Sent like_update message to client.")

    async def disconnect(self, close_code):
        print(f"FeedConsumer: WebSocket disconnecting from group {self.group_name}...") # Logging
        # Leave room group
        if hasattr(self, 'group_name'): # Check if group_name was set
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        print("FeedConsumer: WebSocket disconnected.") # Logging

    # --- UPDATED: Handler for new feed items (SharedListPost OR UserContent) ---
    async def feed_new_item(self, event):
        message_data = event['data'] # Get the JSON data sent by the signal
        # The 'type' inside message_data differentiates the item type
        item_type = message_data.get('type')
        print(f"FeedConsumer: Received feed_new_item of type '{item_type}': {message_data}") # Logging

        # Send JSON data to WebSocket client (browser)
        # The JS will need to know how to handle both 'share' and 'list_item' types
        await self.send(text_data=json.dumps({
            'type': 'new_item', # Keep outer type consistent
            'data': message_data, # Send the raw data, including the inner type
        }))
        print(f"FeedConsumer: Sent new_item message (type: {item_type}) to client.") # Logging
    # --- END UPDATE ---


    # --- Handler for new comments ---
    async def feed_new_comment(self, event):
        message_data = event['data']
        print(f"FeedConsumer: Received feed_new_comment: {message_data}") # Logging

        # Send comment data (including HTML) to WebSocket client
        await self.send(text_data=json.dumps({
            'type': 'new_comment', # Tell JS this is a new comment
            'data': message_data,
        }))
        print("FeedConsumer: Sent new_comment message to client.") # Logging

    # --- Handler for like updates ---
    async def feed_like_update(self, event):
        message_data = event['data']
        print(f"FeedConsumer: Received feed_like_update: {message_data}") # Logging

        # Send like update data to WebSocket client
        await self.send(text_data=json.dumps({
            'type': 'like_update', # Tell JS this is a like update
            'data': message_data,
        }))
        print("FeedConsumer: Sent like_update message to client.") # Logging

    # Optional: Keep feed_update if used elsewhere, or remove if feed_new_item replaces it
    # async def feed_update(self, event):
    #     item_html = event.get('html', None)
    #     await self.send(text_data=json.dumps({
    #         'type': 'new_item_html', # Use a different type if keeping both methods
    #         'html': item_html
    #     }))


# --- NotificationConsumer ---
class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close() # Reject unauthenticated users
            print("NotificationConsumer: Unauthenticated user rejected.")
            return

        # Each user joins a group named after their user ID
        self.group_name = f'notifications_user_{self.user.id}'

        # Join user-specific group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        print(f"NotificationConsumer: User {self.user.id} connected to group {self.group_name}")

        # Optionally send current count upon connection
        current_count = await self.get_unread_count()
        await self.send(text_data=json.dumps({
            'type': 'notification_count_update',
            'unread_count': current_count
        }))


    async def disconnect(self, close_code):
        # Ensure user is authenticated before trying to access self.user.id
        if hasattr(self, 'user') and self.user.is_authenticated and hasattr(self, 'group_name'):
            print(f"NotificationConsumer: User {self.user.id} disconnecting from {self.group_name}...")
            # Leave user-specific group
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
            print(f"NotificationConsumer: User {self.user.id} disconnected.")
        else:
             print("NotificationConsumer: Disconnecting an unauthenticated or improperly connected user.")


    # Receive message from user-specific group (triggered by signal)
    async def user_notification(self, event):
        message_data = event['data']
        # Ensure user attribute exists before logging
        user_id = self.user.id if hasattr(self, 'user') else 'Unknown'
        print(f"NotificationConsumer: Received user_notification for {user_id}: {message_data}") # Logging

        # Send message data (e.g., new count) to WebSocket client (browser)
        await self.send(text_data=json.dumps({
            'type': 'notification_count_update', # Tell JS this is just a count update
            'unread_count': message_data.get('unread_count', 0),
            'new_message': message_data.get('message', None) # Optionally send message text for popups
        }))
        print(f"NotificationConsumer: Sent count update to user {user_id}") # Logging

    # Helper to get count asynchronously
    @sync_to_async
    def get_unread_count(self):
         # Check authentication within the async helper too
         if hasattr(self, 'user') and self.user.is_authenticated:
            return Notification.objects.filter(recipient=self.user, read=False).count()
         return 0