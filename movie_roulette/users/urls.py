from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views
from django_ratelimit.decorators import ratelimit

app_name = 'users'

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', ratelimit(key='ip', rate='5/m', method='POST', block=True)(
        auth_views.LoginView.as_view(template_name='users/login.html')
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    # --- Updated Path ---
    path('settings/profile/', views.profile_settings_view, name='profile_settings'),
    path('settings/account/', views.account_settings_view, name='account_settings'),
    path('password_change/',
         auth_views.PasswordChangeView.as_view(
             template_name='users/password_change.html',
             success_url=reverse_lazy('users:password_change_done') # Redirect after success
         ),
         name='password_change'),
    path('password_change/done/',
         auth_views.PasswordChangeDoneView.as_view(
             template_name='users/password_change_done.html'
         ),
         name='password_change_done'),
    # --- Keep password reset URLs ---
    path('password_reset/', ratelimit(key='ip', rate='3/m', method='POST', block=True)(
     auth_views.PasswordResetView.as_view(template_name='users/password_reset.html')
     ), name='password_reset')
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='users/password_reset_done.html'),
         name='password_reset_done'),
    path('reset/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(template_name='users/password_reset_confirm.html'),
         name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='users/password_reset_complete.html'),
         name='password_reset_complete'),
]