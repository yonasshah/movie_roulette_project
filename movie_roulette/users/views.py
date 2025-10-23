from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import SignUpForm, ProfileUpdateForm
from django.contrib import messages

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
def settings_view(request):
    if request.method == 'POST':
        # --- ADD request.FILES ---
        form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your settings have been updated!')
            return redirect('users:settings')
    else:
        form = ProfileUpdateForm(instance=request.user.profile)
    
    return render(request, 'users/settings.html', {'form': form})