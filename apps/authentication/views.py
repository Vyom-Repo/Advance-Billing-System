"""
apps/authentication/views.py

Advance Billing — Authentication Views
========================================
Handles all user authentication flows:
  - Signup
  - Login
  - Logout
  - Email Verification
  - Forgot Password
  - Reset Password

Architecture:
  - Class-based views for clarity and extensibility
  - Form-based validation (no DRF needed — this is a server-rendered app)
  - Brevo email integration is architecture-ready (email sending in next phase)
  - Rate limiting decorators applied to sensitive endpoints
"""

import logging
from typing import Any

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.signing import Signer, BadSignature
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views import View
from django.views.generic import TemplateView
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from apps.common.services.email_service import EmailService

from apps.common.mixins import PageTitleMixin
from .forms import (
    LoginForm,
    SignupForm,
    ForgotPasswordForm,
    ResetPasswordForm,
)

logger = logging.getLogger(__name__)


# =============================================================================
# SIGNUP
# =============================================================================

@method_decorator(ratelimit(key="ip", rate="5/m", block=False), name="post")
class SignupView(PageTitleMixin, View):
    """
    Handles user registration.

    GET  → Display signup form
    POST → Validate, create user, send verification email, redirect
    """

    template_name = "authentication/signup.html"
    page_title = "Create Account — Advance Billing"

    def get(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect("dashboard:index")
        form = SignupForm()
        return render(request, self.template_name, {
            "form": form,
            "page_title": self.page_title,
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        if getattr(request, "limited", False):
            from apps.common.services.rate_limit import build_ratelimit_429_response  # noqa: PLC0415
            return build_ratelimit_429_response(
                request,
                fn=self.post,
                key="ip",
                rate="5/m",
                custom_message="Rate limit exceeded. Please wait before making more signup attempts.",
            )

        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False   # Require email verification before login
            user.save()

            logger.info("New user registered: %s", user.email)

            # Generate verification token
            signer = Signer()
            token = signer.sign(str(user.pk))
            verify_url = request.build_absolute_uri(
                reverse("auth:verify_email", kwargs={"token": token})
            )

            # Send verification email via EmailService
            EmailService.send_verification_email(user, verify_url)

            messages.success(
                request,
                "Account created! Please check your email to verify your account.",
            )
            request.session["verification_email"] = user.email
            return redirect("auth:verification_sent")

        return render(request, self.template_name, {
            "form": form,
            "page_title": self.page_title,
        })


# =============================================================================
# LOGIN
# =============================================================================

@method_decorator(ratelimit(key="ip", rate="10/m", block=False), name="post")
class LoginView(PageTitleMixin, View):
    """
    Handles user authentication.

    GET  → Display login form
    POST → Authenticate, set session, redirect to dashboard (or ?next=)
    """

    template_name = "authentication/login.html"
    page_title = "Sign In — Advance Billing"

    def get(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            return redirect("dashboard:index")
        form = LoginForm()
        return render(request, self.template_name, {
            "form": form,
            "page_title": self.page_title,
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        if getattr(request, "limited", False):
            from apps.common.services.rate_limit import build_ratelimit_429_response  # noqa: PLC0415
            return build_ratelimit_429_response(
                request,
                fn=self.post,
                key="ip",
                rate="10/m",
                custom_message="Rate limit exceeded. Please wait before making more login attempts.",
            )

        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            password = form.cleaned_data["password"]

            # Django's ModelBackend rejects inactive users by default.
            # We look up the user by email and check the password manually first 
            # so we can intercept unverified users.
            try:
                user_obj = User.objects.get(email=email)
            except User.DoesNotExist:
                user_obj = None

            if user_obj and user_obj.check_password(password):
                if not user_obj.is_active:
                    # User exists and password is correct, but email isn't verified.
                    request.session["verification_email"] = user_obj.email
                    messages.warning(
                        request,
                        "Your email address has not been verified yet. "
                        "Please check your inbox for the verification link.",
                    )
                    return redirect("auth:verification_sent")

                # If active, run through standard authenticate to get the backend attached
                user = authenticate(request, username=user_obj.username, password=password)
                if user is not None:
                    login(request, user)
                    logger.info("User logged in: %s", user.email)

                    next_url = request.GET.get("next", "")
                    if next_url and next_url.startswith("/"):
                        return redirect(next_url)
                    return redirect("dashboard:index")

            messages.error(request, "Invalid email or password. Please try again.")

        return render(request, self.template_name, {
            "form": form,
            "page_title": self.page_title,
        })


# =============================================================================
# LOGOUT
# =============================================================================

class LogoutView(View):
    """
    Logs out the user and redirects to login.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        logout(request)
        messages.info(request, "You have been signed out.")
        return redirect("auth:login")

    def post(self, request: HttpRequest) -> HttpResponse:
        logout(request)
        messages.info(request, "You have been signed out.")
        return redirect("auth:login")


# =============================================================================
# EMAIL VERIFICATION
# =============================================================================

class VerificationSentView(PageTitleMixin, TemplateView):
    """Informational page telling the user to check their email."""
    template_name = "authentication/verification_sent.html"
    page_title = "Check Your Email — Advance Billing"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["email"] = self.request.session.get("verification_email", "")
        return context


class VerifyEmailView(PageTitleMixin, View):
    """
    Handles the link clicked from the user's email.
    Token format: django Signer token of str(user.pk).
    """

    template_name = "authentication/verify_email.html"
    page_title = "Email Verification — Advance Billing"

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        signer = Signer()
        try:
            user_id = signer.unsign(token)
            user = User.objects.get(pk=user_id)
            if not user.is_active:
                user.is_active = True
                user.save()
                logger.info("User verified email successfully: %s", user.email)
                messages.success(request, "Your email has been verified! You can now sign in.")
                return redirect("auth:login")
            else:
                messages.info(request, "Your account is already verified. Please sign in.")
                return redirect("auth:login")
        except (BadSignature, User.DoesNotExist):
            logger.warning("Invalid or expired verification token used.")
            return render(request, self.template_name, {
                "success": False,
                "error": "The verification link is invalid or has expired.",
                "page_title": self.page_title,
            })


@method_decorator(ratelimit(key="ip", rate="5/m", block=False), name="post")
class ResendVerificationEmailView(View):
    """Handles resending the verification email."""
    
    def post(self, request: HttpRequest) -> HttpResponse:
        is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest" or request.headers.get("accept") == "application/json"

        if getattr(request, "limited", False):
            from apps.common.services.rate_limit import build_ratelimit_429_response  # noqa: PLC0415
            return build_ratelimit_429_response(
                request,
                fn=self.post,
                key="ip",
                rate="5/m",
                is_json=is_ajax,
                custom_message="Rate limit exceeded. Please wait before requesting another verification email.",
            )

        email = request.session.get("verification_email")
        
        if not email:
            if is_ajax:
                return JsonResponse({"status": "error", "message": "Session expired. Please log in again to resend the email."}, status=400)
            messages.error(request, "Session expired. Please log in again to resend the email.")
            return redirect("auth:login")
            
        try:
            user = User.objects.get(email=email)
            if user.is_active:
                if is_ajax:
                    return JsonResponse({"status": "info", "message": "Your account is already verified. Please sign in."})
                messages.info(request, "Your account is already verified. Please sign in.")
                return redirect("auth:login")
                
            signer = Signer()
            token = signer.sign(str(user.pk))
            verify_url = request.build_absolute_uri(
                reverse("auth:verify_email", kwargs={"token": token})
            )

            # Send verification email via EmailService
            sent = EmailService.send_verification_email(user, verify_url)
            if sent:
                if is_ajax:
                    return JsonResponse({"status": "success", "message": "Verification email sent successfully."})
                messages.success(request, "Verification email has been resent. Please check your inbox.")
            else:
                if is_ajax:
                    return JsonResponse({"status": "error", "message": "Failed to send email. Please try again later."}, status=500)
                messages.error(request, "Failed to send email. Please try again later.")
        except User.DoesNotExist:
            if is_ajax:
                return JsonResponse({"status": "success", "message": "Verification email sent successfully."})
            pass  # Failsafe, don't expose that user doesn't exist
            
        return redirect("auth:verification_sent")


# =============================================================================
# FORGOT PASSWORD
# =============================================================================

@method_decorator(ratelimit(key="ip", rate="5/m", block=False), name="post")
class ForgotPasswordView(PageTitleMixin, View):
    """
    Step 1 of password reset: user enters their email address.
    Generates secure token and dispatches reset link via Brevo SMTP.
    """

    template_name = "authentication/forgot_password.html"
    page_title = "Reset Password — Advance Billing"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = ForgotPasswordForm()
        return render(request, self.template_name, {
            "form": form,
            "page_title": self.page_title,
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        if getattr(request, "limited", False):
            from apps.common.services.rate_limit import build_ratelimit_429_response  # noqa: PLC0415
            return build_ratelimit_429_response(
                request,
                fn=self.post,
                key="ip",
                rate="5/m",
                custom_message="Rate limit exceeded. Please wait before requesting another password reset.",
            )

        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower().strip()
            logger.info("Password reset requested for: %s", email)
            request.session["reset_email"] = email

            try:
                user = User.objects.get(email__iexact=email, is_active=True)
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                relative_url = reverse("auth:password_reset_confirm", kwargs={"uidb64": uid, "token": token})
                site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")
                reset_url = f"{site_url}{relative_url}"

                sent = EmailService.send_password_reset_email(user, reset_url)
                if sent:
                    logger.info("Password reset token generated and email dispatched for: %s", email)
                else:
                    logger.error("Failed to send password reset email to: %s", email)
            except User.DoesNotExist:
                logger.info("Password reset requested for non-existent or inactive email: %s", email)

            return redirect("auth:password_reset_done")

        return render(request, self.template_name, {
            "form": form,
            "page_title": self.page_title,
        })


class PasswordResetDoneView(PageTitleMixin, TemplateView):
    """Confirmation page shown after requesting password reset."""
    template_name = "authentication/password_reset_done.html"
    page_title = "Check Your Email — Advance Billing"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["email"] = self.request.session.get("reset_email", "")
        return context


# =============================================================================
# RESET PASSWORD
# =============================================================================

class ResetPasswordView(PageTitleMixin, View):
    """
    Step 2 of password reset: user sets a new password using uidb64 + token from email.
    """

    template_name = "authentication/reset_password.html"
    page_title = "Set New Password — Advance Billing"

    def get_user(self, uidb64: str) -> User | None:
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            return User.objects.get(pk=uid, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return None

    def get(self, request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
        user = self.get_user(uidb64)
        valid_link = user is not None and default_token_generator.check_token(user, token)

        if not valid_link:
            logger.warning("Invalid or expired password reset link accessed for uidb64: %s", uidb64)

        form = ResetPasswordForm()
        return render(request, self.template_name, {
            "form": form,
            "uidb64": uidb64,
            "token": token,
            "valid_link": valid_link,
            "page_title": self.page_title,
        })

    def post(self, request: HttpRequest, uidb64: str, token: str) -> HttpResponse:
        user = self.get_user(uidb64)
        valid_link = user is not None and default_token_generator.check_token(user, token)

        if not valid_link:
            messages.error(request, "The password reset link is invalid or has expired.")
            return redirect("auth:forgot_password")

        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data["password1"]
            user.set_password(new_password)
            user.save()
            logger.info("Password reset successfully completed for user: %s", user.email)
            request.session.pop("reset_email", None)
            return redirect("auth:password_reset_complete")

        return render(request, self.template_name, {
            "form": form,
            "uidb64": uidb64,
            "token": token,
            "valid_link": True,
            "page_title": self.page_title,
        })


class PasswordResetCompleteView(PageTitleMixin, TemplateView):
    """Confirmation page shown after successfully setting a new password."""
    template_name = "authentication/password_reset_complete.html"
    page_title = "Password Reset Complete — Advance Billing"
