from django.db import models
from django.conf import settings
from django.dispatch import receiver
from django.db.models.signals import post_save

    
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