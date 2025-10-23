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
        # --- ADD 'image' TO FIELDS ---
        fields = ['image', 'is_favorites_private', 'bio']
        labels = {
            'image': 'Profile Picture',
            'is_favorites_private': 'Make Favorites List Private',
            'bio': 'About Me'
        }
        widgets = {
            'bio': forms.Textarea(attrs={
                'rows': 3,
                'class': 'mt-1 block w-full px-3 py-2 border border-gray-700 bg-gray-900 rounded-md placeholder-gray-500 text-white focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm'
            }),
            'is_favorites_private': forms.CheckboxInput(attrs={
                'class': 'h-6 w-6 text-indigo-600 bg-gray-900 border-gray-700 rounded focus:ring-indigo-500'
            }),
            # --- ADDED WIDGET FOR IMAGE ---
            'image': forms.ClearableFileInput(attrs={
                'class': 'mt-1 block w-full text-sm text-gray-400 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-600 file:text-white hover:file:bg-indigo-700'
            })
        }