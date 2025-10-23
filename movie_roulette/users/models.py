from django.db import models
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from PIL import Image

class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_favorites_private = models.BooleanField(default=False)
    bio = models.TextField(max_length=500, blank=True)
    image = models.ImageField(default='default.jpg', upload_to='profile_pics')

    def __str__(self):
        return f'{self.user.username} Profile'

    # --- Updated save method ---
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs) # Save the profile instance first

        # Construct the expected URL path for the default image
        # Ensure MEDIA_URL ends with a slash in settings.py
        default_image_url = f"{settings.MEDIA_URL}default.jpg"

        # Check if the image field has a file associated with it AND
        # if its URL is different from the default image URL.
        # This prevents resizing the original default.jpg file.
        if self.image and self.image.url != default_image_url:
            try:
                # Now self.image.path should be correct for uploaded files
                img = Image.open(self.image.path)

                if img.height > 300 or img.width > 300:
                    output_size = (300, 300)
                    img.thumbnail(output_size)
                    img.save(self.image.path) # Overwrite the uploaded image file
            except FileNotFoundError:
                # Handle cases where the file might be missing unexpectedly
                # You could log this error if needed
                print(f"Warning: Image file not found at {self.image.path} during resize attempt.")
            except Exception as e:
                # Catch other potential errors during image processing
                print(f"Error resizing image {self.image.path}: {e}")
    # --- End Updated save method ---

# This signal ensures a Profile is created automatically for each new User
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()