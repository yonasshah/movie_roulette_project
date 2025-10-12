from django.shortcuts import render, redirect
from django.contrib.auth import login
from .forms import SignUpForm

def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Log the user in immediately after they sign up
            login(request, user)
            # Redirect to the main movie roulette page
            return redirect('movie_roulette:roulette_view')
    else:
        form = SignUpForm()
    return render(request, 'users/signup.html', {'form': form})