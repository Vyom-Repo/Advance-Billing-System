"""
apps/common/context_processors.py

Advance Billing — Global Template Context Processors
======================================================
These processors inject variables into EVERY template context.

Processors registered:
  - theme_context: injects current theme and available themes
  - app_context: injects global app metadata (name, version, etc.)
"""

from typing import Any

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import DatabaseError
from django.http import HttpRequest


def theme_context(request: HttpRequest) -> dict[str, Any]:
    """
    Injects theme configuration into all templates.
    """
    current_theme = settings.DEFAULT_THEME
    
    if request.user.is_authenticated:
        try:
            current_theme = request.user.preference.theme
        except Exception:
            # Fallback to session if preference object doesn't exist yet
            current_theme = request.session.get("theme", settings.DEFAULT_THEME)
    else:
        current_theme = request.session.get("theme", settings.DEFAULT_THEME)

    return {
        "current_theme": current_theme,
        "available_themes": settings.AVAILABLE_THEMES,
        "default_theme": settings.DEFAULT_THEME,
    }


def app_context(request: HttpRequest) -> dict[str, Any]:
    """
    Injects global application metadata into all templates.

    Templates can use:
        {{ APP_NAME }}      - "Advance Billing"
        {{ APP_TAGLINE }}   - marketing tagline
        {{ APP_VERSION }}   - "1.0.0"
        {{ user_org }}      - the current user's organization (if authenticated)
    """
    context: dict[str, Any] = {
        "APP_NAME": settings.APP_NAME,
        "APP_TAGLINE": settings.APP_TAGLINE,
        "APP_VERSION": settings.APP_VERSION,
    }

    # Inject the user's organization and notification unread count if authenticated
    if request.user.is_authenticated:
        try:
            from apps.organization.models import Organization  # noqa: PLC0415
            user_org = Organization.objects.filter(
                owner=request.user
            ).first()
            context["user_org"] = user_org

            from apps.common.models import Notification  # noqa: PLC0415
            n_qs = Notification.objects.filter(user=request.user, is_read=False)
            if user_org:
                n_qs = n_qs.filter(organization=user_org)
            context["unread_notifications_count"] = n_qs.count()
        except (ObjectDoesNotExist, AttributeError, DatabaseError):
            context["user_org"] = None
            context["unread_notifications_count"] = 0
    else:
        context["user_org"] = None
        context["unread_notifications_count"] = 0

    return context
