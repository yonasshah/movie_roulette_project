from django.db import models
from django.conf import settings

# The model has been renamed from UserMovie to UserContent to reflect that it now handles both.
class UserContent(models.Model):
    # This class defines the types of lists a user can have (Favorites or History).
    class ListType(models.TextChoices):
        FAVORITE = 'FAVORITE', 'Favorite'
        HISTORY = 'HISTORY', 'History'

    # This NEW class distinguishes between Movies and TV Shows.
    class ContentType(models.TextChoices):
        MOVIE = 'MOVIE', 'Movie'
        TV = 'TV', 'TV Show'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # The 'movie_id' field has been renamed to 'tmdb_id' to be more generic.
    tmdb_id = models.IntegerField() 
    
    title = models.CharField(max_length=255)
    poster_path = models.CharField(max_length=255, blank=True, null=True)
    release_year = models.CharField(max_length=4, blank=True, null=True)
    list_type = models.CharField(max_length=10, choices=ListType.choices)
    
    # This NEW field stores whether the item is a movie or a TV show.
    content_type = models.CharField(max_length=10, choices=ContentType.choices, default=ContentType.MOVIE)
    
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        # The 'unique_together' constraint has been updated to include the new 'content_type' field.
        # This ensures a user can't have the same movie and TV show in the same list.
        unique_together = ('user', 'tmdb_id', 'list_type', 'content_type')
        ordering = ['-timestamp']

    def __str__(self):
        # The string representation is updated to work with the new model name.
        return f"{self.user.username} - {self.title} ({self.get_list_type_display()})"
    
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