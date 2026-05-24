from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm, ProfileUpdateForm
from django.contrib import messages
from django_ratelimit.decorators import ratelimit

@ratelimit(key='ip', rate='5/m', method='POST', block=True)
def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Log the user in immediately after they sign up
            login(request, user)
            # Redirect to the main movie roulette page
            return redirect('roulette:roulette_view')
    else:
        form = SignUpForm()
    return render(request, 'users/signup.html', {'form': form})

@login_required
def profile_settings_view(request): # Renamed from settings_view
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile settings have been updated!')
            return redirect('users:profile_settings') # Update redirect
    else:
        form = ProfileUpdateForm(instance=request.user.profile)

    return render(request, 'users/profile_settings.html', {'form': form}) # Update template name

@login_required
def account_settings_view(request):
    """Displays links to account management pages."""
    return render(request, 'users/account_settings.html')
