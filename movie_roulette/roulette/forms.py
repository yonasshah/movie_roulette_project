from django import forms
# --- Make sure you import UserList from models ---
from .models import UserList 

class UserListForm(forms.ModelForm):
    name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter list name (e.g., Sci-Fi Favorites)',
            'class': 'w-full px-3 py-2 border border-gray-700 bg-gray-900 rounded-md placeholder-gray-500 text-white focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm'
        })
    )

    class Meta:
        model = UserList
        fields = ['name']