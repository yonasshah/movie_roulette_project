from django.contrib import admin

from movie_roulette.roulette.models import UserContent, UserFollow
from movie_roulette.users.models import Profile

# Register your models here.

admin.site.register(Profile)

@admin.register(UserContent)
class UserContentAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'list_type', 'content_type', 'timestamp')
    list_filter = ('list_type', 'content_type', 'user')
    search_fields = ('title', 'user__username')

@admin.register(UserFollow)
class UserFollowAdmin(admin.ModelAdmin):
    list_display = ('follower', 'followed')
    search_fields = ('follower__username', 'followed__username')
