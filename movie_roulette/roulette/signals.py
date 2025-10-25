# roulette/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.template.loader import render_to_string
from .models import SharedListPost # Import the model here

@receiver(post_save, sender=SharedListPost) # Adjust sender model if needed later
def broadcast_new_feed_item(sender, instance, created, **kwargs):
    if created: # Only broadcast newly created items
        channel_layer = get_channel_layer()
        group_name = 'feed_updates'

        # Render HTML on the backend
        # Note: Rendering templates outside requests needs care, context might be limited
        try:
            # Add basic context; adjust if your template needs more
            context = {'item': instance}
            # If your template snippet requires the 'request' object (e.g., for request.user),
            # you might need to reconsider sending JSON instead, or simplify the snippet.
            # context['request'] = None # Or find a way to pass a mock request if absolutely necessary
            item_html = render_to_string('roulette/_feed_item_shared_list.html', context)
        except Exception as e:
            print(f"Error rendering template for signal: {e}")
            item_html = None # Avoid sending broken HTML

        if item_html: # Only send if rendering was successful
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'feed.update', # Corresponds to method name in consumer (feed_update)
                    'html': item_html # Send pre-rendered HTML
                }
            )
        else:
             print(f"Signal for SharedListPost {instance.id} skipped due to template render error.")

# --- Add receivers for other models (Review, Comment, Like) here later if needed ---
# Example:
# @receiver(post_save, sender=Comment)
# def broadcast_new_comment(sender, instance, created, **kwargs):
#     if created:
#         # ... similar logic to get channel_layer, group_name ...
#         # ... determine target feed item, render comment HTML ...
#         # ... send message via channel_layer.group_send ...
#         pass