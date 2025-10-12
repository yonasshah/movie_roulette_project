from django.db import models
from django.conf import settings

class UserMovie(models.Model):
    class ListType(models.TextChoices):
        FAVORITE = 'FAVORITE', 'Favorite'
        HISTORY = 'HISTORY', 'History'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    movie_id = models.IntegerField() 
    title = models.CharField(max_length=255)
    poster_path = models.CharField(max_length=255, blank=True, null=True)
    release_year = models.CharField(max_length=4, blank=True, null=True)
    list_type = models.CharField(max_length=10, choices=ListType.choices)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'movie_id', 'list_type')
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.title} ({self.get_list_type_display()})"
