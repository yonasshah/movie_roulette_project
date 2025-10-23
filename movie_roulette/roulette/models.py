from django.db import models
from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
# --- ADDED FOR REVIEW VALIDATORS ---
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


class UserList(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='custom_lists')
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ('user', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (by {self.user.username})"

class UserFollow(models.Model):
    # The user who is initiating the follow (e.g., Jane)
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='following', on_delete=models.CASCADE)
    
    # The user being followed (e.g., Joe)
    followed = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='followers', on_delete=models.CASCADE)

    # --- ADDED TIMESTAMP FOR FEED ---
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        # Ensures a user can only follow another user once
        unique_together = ('follower', 'followed')
        verbose_name = "User Follow"
        verbose_name_plural = "User Follows"

    def __str__(self):
        return f"{self.follower.username} follows {self.followed.username}"
    
# The model has been renamed from UserMovie to UserContent to reflect that it now handles both.
class UserContent(models.Model):
    # This class defines the types of lists a user can have
    class ListType(models.TextChoices):
        FAVORITE = 'FAVORITE', 'Favorite'
        HISTORY = 'HISTORY', 'History'
        WATCHLIST = 'WATCHLIST', 'Watchlist'
        # --- ADD THIS CHOICE ---
        CUSTOM = 'CUSTOM', 'Custom' 

    # This NEW class distinguishes between Movies and TV Shows.
    class ContentType(models.TextChoices):
        MOVIE = 'MOVIE', 'Movie'
        TV = 'TV', 'TV Show'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    tmdb_id = models.IntegerField() 
    
    title = models.CharField(max_length=255)
    poster_path = models.CharField(max_length=255, blank=True, null=True)
    release_year = models.CharField(max_length=4, blank=True, null=True)
    
    # --- UPDATE choices AND max_length (just in case 'WATCHLIST' or 'CUSTOM' is longer) ---
    list_type = models.CharField(max_length=10, choices=ListType.choices)
    
    content_type = models.CharField(max_length=10, choices=ContentType.choices, default=ContentType.MOVIE)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    # --- ADD A LINK TO THE CUSTOM LIST MODEL (defined in the previous step) ---
    custom_list = models.ForeignKey(
        UserList,  # Make sure the UserList model is defined *before* this class
        on_delete=models.CASCADE, 
        related_name='items', 
        null=True, 
        blank=True 
    )
    # --- END ADDED FIELD ---

    class Meta:
        # --- UPDATE unique_together --- 
        # Prevents duplicates in built-in lists or *within the same* custom list.
        # Allows an item to be in Favorites AND a custom list simultaneously.
        unique_together = ('user', 'tmdb_id', 'content_type', 'list_type', 'custom_list')
        ordering = ['-timestamp']

    # --- UPDATE __str__ TO SHOW CUSTOM LIST NAME ---
    def __str__(self):
        list_name = self.get_list_type_display()
        # If it's a custom list item AND linked to a list, show the list's name
        if self.list_type == self.ListType.CUSTOM and self.custom_list:
            list_name = self.custom_list.name
        return f"{self.user.username} - {self.title} ({list_name})"

# --- NEW MODEL FOR REVIEWS ---
class UserReview(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    tmdb_id = models.IntegerField()
    content_type = models.CharField(max_length=10, choices=UserContent.ContentType.choices)
    
    # Rating from 1 (0.5 stars) to 10 (5 stars)
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(10)]
    )
    review_text = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Store basic info for display in feeds, so we don't have to hit the API
    title = models.CharField(max_length=255, default='')
    poster_path = models.CharField(max_length=255, blank=True, null=True, default='')

    class Meta:
        unique_together = ('user', 'tmdb_id', 'content_type')
        ordering = ['-timestamp']

    def __str__(self):
        return f"Review by {self.user.username} for {self.title} ({self.rating}/10)"

class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField(max_length=500)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Generic relation to link to UserReview OR UserContent
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['timestamp'] # Show oldest comments first

    def __str__(self):
        return f'Comment by {self.user.username} on {self.content_object}'

# --- NEW LIKE MODEL ---
class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes')
    timestamp = models.DateTimeField(auto_now_add=True)

    # Generic relation to link to UserReview OR UserContent
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        unique_together = ('user', 'content_type', 'object_id') # User can only like an item once
        ordering = ['-timestamp']

    def __str__(self):
        return f'Like by {self.user.username} on {self.content_object}'
    
class Notification(models.Model):
    # User who should receive the notification
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='notifications', on_delete=models.CASCADE)
    # User who performed the action (optional, e.g., system notifications might not have an actor)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='actions', on_delete=models.CASCADE, null=True, blank=True)
    # Verb describing the action (e.g., 'liked', 'commented on', 'followed')
    verb = models.CharField(max_length=255)
    # The object that was acted upon (optional, e.g., a review, a list item, or None for a follow)
    target_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, related_name='target_notifications')
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey('target_content_type', 'target_object_id')
    # Timestamp of the action
    timestamp = models.DateTimeField(default=timezone.now) # Use timezone.now
    # Read status
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp'] # Show newest first

    def __str__(self):
        if self.target:
            return f'{self.actor} {self.verb} {self.target} ({self.recipient})'
        elif self.actor:
             return f'{self.actor} {self.verb} ({self.recipient})'
        else:
             return f'{self.verb} ({self.recipient})'