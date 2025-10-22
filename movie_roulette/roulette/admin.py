from django.contrib import admin

from .models import UserContent, UserFollow

# Register your models here.
@admin.register(UserContent)
class UserContentAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'list_type', 'content_type', 'timestamp')
    list_filter = ('list_type', 'content_type', 'user')
    search_fields = ('title', 'user__username')

@admin.register(UserFollow)
class UserFollowAdmin(admin.ModelAdmin):
    list_display = ('follower', 'followed')
    search_fields = ('follower__username', 'followed__username')
