from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Profile

class SignUpForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

# --- ADD THIS FORM ---
class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['is_favorites_private', 'bio'] # --- ADD 'bio' HERE ---
        labels = {
            'is_favorites_private': 'Make Favorites List Private',
            'bio': 'About Me' # --- ADD THIS LABEL ---
        }
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3}) # --- ADD THIS WIDGET ---
        }