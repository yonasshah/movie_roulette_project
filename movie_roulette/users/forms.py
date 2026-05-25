from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Profile
from PIL import Image

class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

# --- ADD THIS FORM ---
class ProfileUpdateForm(forms.ModelForm):
    GENRE_CHOICES = [
        ("Action", "Action"),
        ("Adventure", "Adventure"),
        ("Animation", "Animation"),
        ("Comedy", "Comedy"),
        ("Crime", "Crime"),
        ("Documentary", "Documentary"),
        ("Drama", "Drama"),
        ("Fantasy", "Fantasy"),
        ("Horror", "Horror"),
        ("Mystery", "Mystery"),
        ("Romance", "Romance"),
        ("Sci-Fi", "Sci-Fi"),
        ("Thriller", "Thriller"),
    ]

    favorite_genres = forms.MultipleChoiceField(
        choices=GENRE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Profile
        fields = [
            "display_name",
            "image",
            "banner_image",
            "bio",
            "favorite_genres",
            "favorite_movie_title",
            "favorite_movie_tmdb_id",
            "favorite_show_title",
            "favorite_show_tmdb_id",
            "is_favorites_private",
            "is_watchlist_private",
            "is_reviews_private",
            "is_activity_private",
            "is_profile_private",
        ]

        labels = {
            "display_name": "Display name",
            "image": "Profile picture",
            "banner_image": "Profile banner",
            "bio": "About me",
            "favorite_genres": "Favorite genres",
            "favorite_movie_title": "Favorite movie",
            "favorite_show_title": "Favorite show",
            "is_favorites_private": "Hide favorites",
            "is_watchlist_private": "Hide watchlist",
            "is_reviews_private": "Hide reviews",
            "is_activity_private": "Hide activity",
            "is_profile_private": "Make profile private",
        }

        widgets = {
            "display_name": forms.TextInput(attrs={
                "placeholder": "Yonas, AFK Wook, etc.",
                "class": "settings-text-input"
            }),
            "bio": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Tell people about your movie taste...",
                "class": "settings-textarea"
            }),
            "favorite_movie_title": forms.TextInput(attrs={
                "placeholder": "The Dark Knight",
                "class": "settings-text-input"
            }),
            "favorite_movie_tmdb_id": forms.HiddenInput(),
            "favorite_show_title": forms.TextInput(attrs={
                "placeholder": "The Boys",
                "class": "settings-text-input"
            }),
            "favorite_show_tmdb_id": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance and self.instance.favorite_genres:
            self.initial["favorite_genres"] = [
                genre.strip()
                for genre in self.instance.favorite_genres.split(",")
                if genre.strip()
            ]
            
    def clean_image(self):
        image = self.cleaned_data.get("image")
        return self.validate_uploaded_image(image, "Profile picture")


    def clean_banner_image(self):
        image = self.cleaned_data.get("banner_image")
        return self.validate_uploaded_image(image, "Banner image")


    def validate_uploaded_image(self, image, field_name):
        if not image:
            return image

        max_size_mb = 3
        if image.size > max_size_mb * 1024 * 1024:
            raise forms.ValidationError(f"{field_name} must be under {max_size_mb}MB.")

        allowed_content_types = ["image/jpeg", "image/png", "image/webp"]
        content_type = getattr(image, "content_type", "")

        if content_type not in allowed_content_types:
            raise forms.ValidationError(
                f"{field_name} must be a JPG, PNG, or WebP image."
            )

        try:
            img = Image.open(image)
            img.verify()
        except Exception:
            raise forms.ValidationError(f"{field_name} is not a valid image.")

        return image

    def clean_favorite_genres(self):
        genres = self.cleaned_data.get("favorite_genres", [])

        if genres and len(genres) < 3:
            raise forms.ValidationError("Choose at least 3 genres or leave this blank.")

        if len(genres) > 5:
            raise forms.ValidationError("Choose up to 5 favorite genres.")

        return ",".join(genres)