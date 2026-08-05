"""
apps/common/services/email_service.py
Advance Billing — Centralized Production Email Service
"""

import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


class EmailService:
    """
    Centralized email service for Advance Billing.
    Renders modular HTML email templates (extending emails/base_email.html)
    and sends multi-part HTML/Text emails via Django's SMTP configuration.
    """

    @classmethod
    def send_verification_email(cls, user, verify_url: str) -> bool:
        """
        Sends a responsive HTML email verification link to a user.
        """
        subject = "Verify your Advance Billing account"
        recipient_email = user.email

        # Get first name or default email username
        first_name = ""
        if hasattr(user, "first_name") and user.first_name:
            first_name = user.first_name
        else:
            first_name = recipient_email.split("@")[0]

        context = {
            "user": user,
            "first_name": first_name.capitalize(),
            "verify_url": verify_url,
            "site_url": getattr(settings, "SITE_URL", "http://127.0.0.1:8000"),
            "support_email": getattr(settings, "SERVER_EMAIL", "advancebillingbyvyom@gmail.com"),
            "app_name": getattr(settings, "APP_NAME", "Advance Billing"),
            "app_tagline": getattr(settings, "APP_TAGLINE", "GST Billing Made Simple"),
        }

        try:
            html_content = render_to_string("emails/verification_email.html", context)
            text_content = strip_tags(html_content)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)

            logger.info("Verification email successfully sent to: %s", recipient_email)
            return True
        except Exception as e:
            logger.error("Failed to send verification email to %s: %s", recipient_email, str(e))
            return False

    @classmethod
    def send_password_reset_email(cls, user, reset_url: str) -> bool:
        """
        Sends a responsive HTML password reset link to a user.
        """
        subject = "Reset your Advance Billing password"
        recipient_email = user.email

        first_name = ""
        if hasattr(user, "first_name") and user.first_name:
            first_name = user.first_name
        else:
            first_name = recipient_email.split("@")[0]

        context = {
            "user": user,
            "first_name": first_name.capitalize(),
            "reset_url": reset_url,
            "site_url": getattr(settings, "SITE_URL", "http://127.0.0.1:8000"),
            "support_email": getattr(settings, "SERVER_EMAIL", "advancebillingbyvyom@gmail.com"),
            "app_name": getattr(settings, "APP_NAME", "Advance Billing"),
            "app_tagline": getattr(settings, "APP_TAGLINE", "GST Billing Made Simple"),
        }

        try:
            html_content = render_to_string("emails/password_reset_email.html", context)
            text_content = strip_tags(html_content)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)

            logger.info("Password reset email successfully sent to: %s", recipient_email)
            return True
        except Exception as e:
            logger.error("Failed to send password reset email to %s: %s", recipient_email, str(e), exc_info=True)
            return False
