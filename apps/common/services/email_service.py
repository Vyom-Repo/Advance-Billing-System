"""
apps/common/services/email_service.py
Advance Billing — Centralized Production Email Service & Product Branding System
"""

import logging
from typing import Any, Dict
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


class AdvanceBillingEmailBranding:
    """
    Official Advance Billing Product Email Branding.

    STRICT BEHAVIOR MANDATE:
    All emails sent by Advance Billing MUST use Advance Billing product-level
    branding exclusively (logo, brand colors, Lora font, Advance Billing header & footer).

    Organization/company branding (logos, colors, invoice design) belongs strictly
    to customer-facing document/PDF rendering and MUST NEVER be used to alter
    the visual presentation of outgoing email shells.
    """

    @classmethod
    def get_email_branding(cls) -> Dict[str, Any]:
        """
        Returns the immutable, official Advance Billing product email branding context.
        """
        site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")
        app_name = getattr(settings, "APP_NAME", "Advance Billing")
        app_tagline = getattr(settings, "APP_TAGLINE", "GST Billing Made Simple for Indian Businesses")

        from email.utils import parseaddr

        raw_setting = (
            getattr(settings, "SUPPORT_EMAIL", None)
            or getattr(settings, "SERVER_EMAIL", None)
            or "advancebillingbyvyom@gmail.com"
        )
        parsed_name, parsed_addr = parseaddr(str(raw_setting))

        support_email_address = parsed_addr.strip() if (parsed_addr and "@" in parsed_addr) else "advancebillingbyvyom@gmail.com"
        support_display_name = parsed_name.strip() if parsed_name else app_name
        support_email_display = f"{support_display_name} <{support_email_address}>"

        is_production = (
            site_url.startswith("https://")
            and "127.0.0.1" not in site_url
            and "localhost" not in site_url
        )
        logo_url = f"{site_url}/static/branding/logo-email.png" if is_production else ""

        return {
            "brand_name": app_name,
            "app_name": app_name,
            "tagline": app_tagline,
            "logo_url": logo_url,
            "primary_color": "#1E293B",      # Sleek Slate/Dark primary header
            "secondary_color": "#FF7A00",    # Signature Advance Billing Orange Accent
            "accent_color": "#FF7A00",
            "text_color": "#111827",
            "body_bg_color": "#F9FAFB",
            "card_bg_color": "#FFFFFF",
            "border_color": "#E5E7EB",
            "muted_text_color": "#6B7280",
            "font_family": "'Lora', Georgia, 'Times New Roman', serif",
            "font_weight": "400",
            "font_style": "italic",
            "font_import_url": "https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400..700;1,400..700&display=swap",
            "support_email": support_email_address,
            "support_email_address": support_email_address,
            "support_email_display_name": support_display_name,
            "support_email_display": support_email_display,
            "support_mailto_url": f"mailto:{support_email_address}",
            "footer_text": f"Powered by {app_name} — {app_tagline}",
            "website": site_url,
        }

    @classmethod
    def resolve(cls, organization=None) -> Dict[str, Any]:
        """Backwards compatibility helper returning product-level branding."""
        return cls.get_email_branding()

    @classmethod
    def get_logo_context(cls) -> Dict[str, str]:
        branding = cls.get_email_branding()
        return {"logo_src": branding["logo_url"]}


# Aliases for backwards compatibility
EmailBrandingService = AdvanceBillingEmailBranding
EmailBranding = AdvanceBillingEmailBranding


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

        first_name = ""
        if hasattr(user, "first_name") and user.first_name:
            first_name = user.first_name
        else:
            first_name = recipient_email.split("@")[0]

        email_branding = AdvanceBillingEmailBranding.get_email_branding()

        context = {
            "email_branding": email_branding,
            "branding": email_branding,
            "user": user,
            "first_name": first_name.capitalize(),
            "verify_url": verify_url,
            "site_url": getattr(settings, "SITE_URL", "http://127.0.0.1:8000"),
            "support_email": email_branding["support_email"],
            "app_name": email_branding["app_name"],
            "app_tagline": email_branding["tagline"],
            "logo_src": email_branding["logo_url"],
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

        email_branding = AdvanceBillingEmailBranding.get_email_branding()

        context = {
            "email_branding": email_branding,
            "branding": email_branding,
            "user": user,
            "first_name": first_name.capitalize(),
            "reset_url": reset_url,
            "site_url": getattr(settings, "SITE_URL", "http://127.0.0.1:8000"),
            "support_email": email_branding["support_email"],
            "app_name": email_branding["app_name"],
            "app_tagline": email_branding["tagline"],
            "logo_src": email_branding["logo_url"],
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

    @classmethod
    def send_otp_email(cls, user, otp_code: str) -> bool:
        """
        Sends a responsive HTML OTP email to a user.
        """
        subject = "Your Advance Billing Verification Code"
        recipient_email = user.email

        first_name = ""
        if hasattr(user, "first_name") and user.first_name:
            first_name = user.first_name
        else:
            first_name = recipient_email.split("@")[0]

        email_branding = AdvanceBillingEmailBranding.get_email_branding()

        context = {
            "email_branding": email_branding,
            "branding": email_branding,
            "user": user,
            "first_name": first_name.capitalize(),
            "otp_code": otp_code,
            "site_url": getattr(settings, "SITE_URL", "http://127.0.0.1:8000"),
            "support_email": email_branding["support_email"],
            "app_name": email_branding["app_name"],
            "app_tagline": email_branding["tagline"],
            "logo_src": email_branding["logo_url"],
        }

        try:
            html_content = render_to_string("emails/otp_email.html", context)
            text_content = strip_tags(html_content)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email],
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)

            logger.info("OTP email successfully sent to: %s", recipient_email)
            return True
        except Exception as e:
            logger.error("Failed to send OTP email to %s: %s", recipient_email, str(e), exc_info=True)
            return False
