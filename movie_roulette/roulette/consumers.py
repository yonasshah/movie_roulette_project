# roulette/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer
# ... other imports if needed

class FeedConsumer(AsyncWebsocketConsumer):
    # ... connect and disconnect methods remain the same ...

    # Receive message from the feed group (triggered by backend signals)
    async def feed_new_item(self, event):
        message_data = event['data'] # Get the JSON data sent by the signal

        # Send JSON data to WebSocket client (browser)
        await self.send(text_data=json.dumps({
            'type': 'new_item', # Tell JS this is a new item
            'data': message_data, # Send the raw data
        }))

    # Optional: Keep feed_update if used elsewhere, or remove if feed_new_item replaces it
    # async def feed_update(self, event):
    #     item_html = event.get('html', None)
    #     await self.send(text_data=json.dumps({
    #         'type': 'new_item_html', # Use a different type if keeping both methods
    #         'html': item_html
    #     }))