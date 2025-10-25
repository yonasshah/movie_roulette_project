# roulette/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async # If needed to access DB
# from .models import ... # Import models if needed
# from django.template.loader import render_to_string # To render HTML snippets

class FeedConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Check if user is authenticated (using AuthMiddlewareStack)
        if self.scope["user"].is_authenticated:
            self.group_name = 'feed_updates' # Name for the group/channel

            # Join feed group
            await self.channel_layer.group_add(
                self.group_name,
                self.channel_name
            )
            await self.accept()
        else:
            await self.close() # Reject unauthenticated users

    async def disconnect(self, close_code):
        # Leave feed group
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    # Receive message from WebSocket (less common for feed updates, usually server pushes)
    # async def receive(self, text_data):
    #     pass

    # Receive message from the feed group (triggered by backend)
    async def feed_update(self, event):
        message_data = event['message'] # e.g., JSON representation of the new item
        item_html = event.get('html', None) # Or pre-rendered HTML

        # Send message to WebSocket client (browser)
        await self.send(text_data=json.dumps({
            'type': 'new_item', # Tell JS what kind of message this is
            'data': message_data, # Send the raw data
            'html': item_html # Or send rendered HTML
        }))

    # Helper to render template snippet asynchronously (optional)
    # @database_sync_to_async
    # def render_item_html(self, item_instance, template_name):
    #    return render_to_string(template_name, {'item': item_instance})