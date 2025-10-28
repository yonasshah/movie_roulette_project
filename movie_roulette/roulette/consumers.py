# roulette/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
# ... other imports if needed

class FeedConsumer(AsyncWebsocketConsumer):
    # ****** ADD connect METHOD ******
    async def connect(self):
        self.group_name = 'feed_updates' # Name of the group

        # Join room group
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()
        print(f"WebSocket connected and added to group {self.group_name}") # Add logging

    # ****** ADD disconnect METHOD ******
    async def disconnect(self, close_code):
        print(f"WebSocket disconnecting from group {self.group_name}...") # Add logging
        # Leave room group
        if hasattr(self, 'group_name'): # Check if group_name was set
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        print("WebSocket disconnected.") # Add logging

    # Receive message from the feed group (triggered by backend signals)
    async def feed_new_item(self, event):
        message_data = event['data'] # Get the JSON data sent by the signal
        print(f"Consumer received feed_new_item: {message_data}") # Add logging

        # Send JSON data to WebSocket client (browser)
        await self.send(text_data=json.dumps({
            'type': 'new_item', # Tell JS this is a new item
            'data': message_data, # Send the raw data
        }))
        print("Consumer sent message to client.") # Add logging

    # Optional: Keep feed_update if used elsewhere, or remove if feed_new_item replaces it
    # async def feed_update(self, event):
    #     item_html = event.get('html', None)
    #     await self.send(text_data=json.dumps({
    #         'type': 'new_item_html', # Use a different type if keeping both methods
    #         'html': item_html
    #     }))