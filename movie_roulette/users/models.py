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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs) # Save the profile instance first

        default_image_url = f"{settings.MEDIA_URL}default.jpg"

        if self.image and self.image.url != default_image_url:
            try:
                img = Image.open(self.image.path)

                # --- Check for EXIF Orientation ---
                try:
                    # Get orientation tag identifier
                    for orientation in ExifTags.TAGS.keys():
                        if ExifTags.TAGS[orientation] == 'Orientation':
                            break
                    
                    exif = dict(img._getexif().items())

                    if exif[orientation] == 3:
                        img = img.rotate(180, expand=True)
                    elif exif[orientation] == 6:
                        img = img.rotate(270, expand=True)
                    elif exif[orientation] == 8:
                        img = img.rotate(90, expand=True)
                except (AttributeError, KeyError, IndexError):
                    # Cases: image doesn't have getexif method, EXIF data missing, or orientation tag missing
                    pass # No EXIF orientation data to apply
                # --- End EXIF Handling ---

                # Continue with resizing
                if img.height > 300 or img.width > 300:
                    output_size = (300, 300)
                    img.thumbnail(output_size)
                
                # Save the potentially rotated and resized image
                img.save(self.image.path)

            except FileNotFoundError:
                print(f"Warning: Image file not found at {self.image.path} during processing attempt.")
            except Exception as e:
                print(f"Error processing image {self.image.path}: {e}")
    # --- End Updated save method ---

# This signal ensures a Profile is created automatically for each new User
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()