"""
apps/authentication/urls.py

Authentication URL routes — namespaced as 'auth'
"""

from django.urls import path
from . import views

app_name = "auth"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("signup/", views.SignupView.as_view(), name="signup"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("verify-email/sent/", views.VerificationSentView.as_view(), name="verification_sent"),
    path("verify-email/resend/", views.ResendVerificationEmailView.as_view(), name="resend_verification"),
    path("verify-email/<str:token>/", views.VerifyEmailView.as_view(), name="verify_email"),
    path("forgot-password/", views.ForgotPasswordView.as_view(), name="forgot_password"),
    path("forgot-password/done/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset-password/<str:uidb64>/<str:token>/", views.ResetPasswordView.as_view(), name="password_reset_confirm"),
    path("reset-password/complete/", views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
