from django.db import models
from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.template.loader import render_to_string
from django.urls import reverse
from django.contrib.contenttypes.fields import GenericRelation # Import GenericRelation


class UserList(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='custom_lists')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True, max_length=500, help_text="Optional: Describe your list.")
    is_public = models.BooleanField(default=True, help_text="Make this list viewable by others?")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ('user', 'name')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} (by {self.user.username})"
    
    def get_absolute_url(self):
        # Returns the URL for this specific list's detail page
        return reverse('roulette:list_detail', kwargs={'list_id': self.id})

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
    overview = models.TextField(blank=True, default='')
    
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
    overview = models.TextField(blank=True, default='')

    class Meta:
        unique_together = ('user', 'tmdb_id', 'content_type')
        ordering = ['-timestamp']

    def __str__(self):
        return f"Review by {self.user.username} for {self.title} ({self.rating}/10)"
    


class Comment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments')
    text = models.TextField(max_length=500)
    timestamp = models.DateTimeField(auto_now_add=True)

    # Generic relation can now link to UserReview, UserContent, OR SharedListPost
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

    # Generic relation can now link to UserReview, UserContent, OR SharedListPost
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        unique_together = ('user', 'content_type', 'object_id')
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

    # Action Object: The object *involved* in the action if different from target (e.g., the UserList being shared)
    action_object_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True, blank=True, related_name='action_object_notifications')
    action_object_object_id = models.PositiveIntegerField(null=True, blank=True)
    action_object = GenericForeignKey('action_object_content_type', 'action_object_object_id')
    # Timestamp of the action
    timestamp = models.DateTimeField(default=timezone.now) # Use timezone.now
    # Read status
    read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-timestamp'] # Show newest first

    def __str__(self):
        # --- Update str method ---
        parts = []
        if self.actor:
            parts.append(f"@{self.actor.username}")
        parts.append(self.verb)

        # Prefer showing action_object for verbs like 'shared'
        if self.action_object and 'shared' in self.verb:
             parts.append(f"'{self.action_object.name}'") # Assuming action_object (UserList) has a 'name'
        elif self.target:
            # Basic string representation of the target
            target_str = str(self.target)
            if hasattr(self.target, 'title'): # For UserContent/UserReview
                target_str = self.target.title
            elif hasattr(self.target, 'username'): # For User (if target is a User)
                target_str = f"@{self.target.username}"
            parts.append(f"'{target_str}'")

        return f"{' '.join(parts)} -> @{self.recipient.username}"
    
class SharedListPost(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shared_list_posts')
    list = models.ForeignKey(UserList, on_delete=models.CASCADE, related_name='shared_in_feeds') # Link to the UserList
    message = models.TextField(blank=True, null=True, max_length=500) # Optional message
    timestamp = models.DateTimeField(auto_now_add=True) # Timestamp of sharing

    # --- Add GenericRelations for Comments and Likes ---
    comments = GenericRelation(Comment)
    likes = GenericRelation(Like)
    # --- End Add ---

    class Meta:
        ordering = ['-timestamp'] # Newest first

    def __str__(self):
        return f"Shared list '{self.list.name}' by @{self.user.username} at {self.timestamp.strftime('%Y-%m-%d %H:%M')}"
    

class Vote(models.Model):
    """Thumbs up/down votes on feed items (reviews, list items, shared posts)."""
    class VoteType(models.IntegerChoices):
        UPVOTE = 1, 'Upvote'
        DOWNVOTE = -1, 'Downvote'
 
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='votes')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    vote_type = models.IntegerField(choices=VoteType.choices)
    timestamp = models.DateTimeField(auto_now_add=True)
 
    class Meta:
        unique_together = ('user', 'content_type', 'object_id')
        ordering = ['-timestamp']
 
    def __str__(self):
        label = 'Upvote' if self.vote_type == 1 else 'Downvote'
        return f'{label} by {self.user.username} on {self.content_object}'