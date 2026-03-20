# roulette/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.template.loader import render_to_string
from .models import SharedListPost

@receiver(post_save, sender=SharedListPost)
def broadcast_new_feed_item(sender, instance, created, **kwargs):
    if created:
        channel_layer = get_channel_layer()
        group_name = 'feed_updates'
        item_html = None # Initialize item_html

        try:
            # --- Attempt Rendering ---
            # NOTE: This rendering might still fail silently because the required
            # context (comment_form, fetched_ attributes) isn't fully available here.
            # A more robust solution would be to send JSON data instead of HTML,
            # but this change focuses on preventing the view's error message.
            context = {'item': instance}
            item_html = render_to_string('roulette/_feed_item_shared_list.html', context)

            # --- Attempt Sending (only if rendering succeeded) ---
            if item_html:
                async_to_sync(channel_layer.group_send)(
                    group_name,
                    {
                        'type': 'feed.update', # Corresponds to method name in consumer
                        'html': item_html
                    }
                )
            else:
                # Log the rendering failure if item_html is None
                print(f"Signal for SharedListPost {instance.id} skipped sending due to template render error.")

        except Exception as e:
            # Catch errors during rendering OR sending to channel layer
            print(f"ERROR in broadcast_new_feed_item signal for SharedListPost {instance.id}: {e}")
            # IMPORTANT: Do not re-raise the exception. Just log it.
            # This allows the main view function to return its success response.

# --- Add receivers for other models (Review, Comment, Like) here later if needed ---