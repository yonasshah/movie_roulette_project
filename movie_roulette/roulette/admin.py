from django.contrib import admin

# --- Import UserReview ---
from .models import UserContent, UserFollow, UserReview

# Register your models here.
@admin.register(UserContent)
class UserContentAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'list_type', 'content_type', 'timestamp')
    list_filter = ('list_type', 'content_type', 'user')
    search_fields = ('title', 'user__username')

@admin.register(UserFollow)
class UserFollowAdmin(admin.ModelAdmin):
    # --- Add timestamp ---
    list_display = ('follower', 'followed', 'timestamp')
    search_fields = ('follower__username', 'followed__username')

# --- ADDED ---
@admin.register(UserReview)
class UserReviewAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'rating', 'content_type', 'timestamp')
    list_filter = ('content_type', 'rating', 'user')
    search_fields = ('title', 'user__username', 'review_text')
