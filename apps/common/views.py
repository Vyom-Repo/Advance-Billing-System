"""
apps/common/views.py

Advance Billing — Common/Shared Views
=======================================
Contains:
  - Health check endpoint (required by Render for zero-downtime deploys)
  - Coming Soon view (placeholder for unbuilt modules)
  - Custom 404 and 500 error handlers
  - Landing page view
"""

import json
import logging
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View
from django.views.generic import TemplateView

logger = logging.getLogger(__name__)


# =============================================================================
# HEALTH CHECK
# =============================================================================

class HealthCheckView(View):
    """
    Public health check endpoint consumed by Render's zero-downtime deploy
    mechanism and any monitoring system.

    Returns JSON with:
        status: "ok"
        version: application version
        environment: current DJANGO_ENV

    HTTP 200 always if Django is alive. Use database checks separately.
    """

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        payload = {
            "status": "ok",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.DJANGO_ENV if hasattr(settings, "DJANGO_ENV") else "unknown",
        }
        return JsonResponse(payload, status=200)


# =============================================================================
# LANDING PAGE
# =============================================================================

class LandingView(TemplateView):
    """
    Public-facing SaaS landing page.
    Redirects authenticated users directly to the dashboard.
    """

    template_name = "landing/index.html"

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        if request.user.is_authenticated:
            from django.shortcuts import redirect
            return redirect("dashboard:index")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"{settings.APP_NAME} — {settings.APP_TAGLINE}"
        context["meta_description"] = (
            "Advance Billing is a modern cloud-based GST billing platform for "
            "Indian businesses. Generate professional invoices, manage customers, "
            "and automate GST calculations."
        )
        return context


class PrivacyPolicyView(TemplateView):
    """
    Public-facing Privacy Policy page.
    Accessible without authentication.
    """

    template_name = "common/privacy_policy.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Privacy Policy — {settings.APP_NAME}"
        context["meta_description"] = (
            f"Privacy Policy for {settings.APP_NAME}. Learn how we collect, process, "
            "store, and protect your business data under applicable Indian laws including the DPDP Act, 2023."
        )
        return context


class TermsOfServiceView(TemplateView):
    """
    Public-facing Terms of Service page.
    Accessible without authentication.
    """

    template_name = "common/terms_of_service.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Terms of Service — {settings.APP_NAME}"
        context["meta_description"] = (
            f"Terms of Service for {settings.APP_NAME}. Understand your rights, responsibilities, "
            "GST disclaimers, free tier availability, and service terms."
        )
        return context


# =============================================================================
# COMING SOON
# =============================================================================

class ComingSoonView(TemplateView):
    """
    Professional placeholder page for modules not yet built.
    Renders with a dynamic module name so one template serves all modules.
    """

    template_name = "coming_soon.html"
    module_name: str = "This Feature"
    module_description: str = "We are working hard to bring this to you."
    expected_version: str = "v1.1"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        context["module_name"] = self.module_name
        context["module_description"] = self.module_description
        context["expected_version"] = self.expected_version
        context["page_title"] = f"{self.module_name} — Coming Soon"
        return context


# =============================================================================
# ERROR HANDLERS
# =============================================================================

def error_404(request: HttpRequest, exception: Exception) -> HttpResponse:
    """Custom 404 handler — professional page rather than Django's default."""
    logger.warning("404 Not Found: %s", request.path)
    return render(request, "404.html", {"page_title": "Page Not Found"}, status=404)


def error_500(request: HttpRequest) -> HttpResponse:
    """Custom 500 handler — professional page rather than Django's default."""
    logger.error("500 Internal Server Error on: %s", request.path)
    return render(request, "500.html", {"page_title": "Server Error"}, status=500)


# =============================================================================
# NOTIFICATION API ENDPOINTS
# =============================================================================

from apps.common.mixins import BillingLoginRequiredMixin  # noqa: E402, PLC0415
from apps.common.models import Notification  # noqa: E402, PLC0415


class NotificationListView(BillingLoginRequiredMixin, View):
    """
    GET /api/notifications/
    Returns the latest 20 notifications for the authenticated user and authorized organization,
    plus the unread_count. Database is single source of truth.
    """

    def get(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        org = getattr(request.user, "organization", None)
        if not org:
            from apps.organization.models import Organization  # noqa: PLC0415
            org = Organization.objects.filter(owner=request.user).first()

        qs = Notification.objects.filter(user=request.user)
        if org:
            qs = qs.filter(organization=org)

        unread_count = qs.filter(is_read=False).count()
        recent_qs = qs.order_by("-created_at")[:20]
        notifications_data = [item.to_dict() for item in recent_qs]

        return JsonResponse({
            "unread_count": unread_count,
            "notifications": notifications_data,
        }, status=200)


class NotificationMarkReadView(BillingLoginRequiredMixin, View):
    """
    POST /api/notifications/<int:pk>/read/
    Marks a single notification as read. Enforces user & org ownership.
    """

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> JsonResponse:
        org = getattr(request.user, "organization", None)
        if not org:
            from apps.organization.models import Organization  # noqa: PLC0415
            org = Organization.objects.filter(owner=request.user).first()

        qs = Notification.objects.filter(id=pk, user=request.user)
        if org:
            qs = qs.filter(organization=org)

        notification = qs.first()
        if not notification:
            return JsonResponse({"error": "Notification not found or access denied"}, status=404)

        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read", "updated_at"])

        count_qs = Notification.objects.filter(user=request.user, is_read=False)
        if org:
            count_qs = count_qs.filter(organization=org)

        return JsonResponse({
            "status": "success",
            "id": notification.id,
            "is_read": True,
            "unread_count": count_qs.count(),
        }, status=200)


class NotificationMarkAllReadView(BillingLoginRequiredMixin, View):
    """
    POST /api/notifications/read-all/
    Marks all notifications for the authenticated user & organization as read.
    """

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        org = getattr(request.user, "organization", None)
        if not org:
            from apps.organization.models import Organization  # noqa: PLC0415
            org = Organization.objects.filter(owner=request.user).first()

        qs = Notification.objects.filter(user=request.user, is_read=False)
        if org:
            qs = qs.filter(organization=org)

        updated_count = qs.update(is_read=True)
        return JsonResponse({
            "status": "success",
            "updated_count": updated_count,
            "unread_count": 0,
        }, status=200)


class NotificationDeleteView(BillingLoginRequiredMixin, View):
    """
    POST /api/notifications/<int:pk>/delete/
    Deletes a single notification. Enforces user & org ownership.
    """

    def post(self, request: HttpRequest, pk: int, *args: Any, **kwargs: Any) -> JsonResponse:
        org = getattr(request.user, "organization", None)
        if not org:
            from apps.organization.models import Organization  # noqa: PLC0415
            org = Organization.objects.filter(owner=request.user).first()

        qs = Notification.objects.filter(id=pk, user=request.user)
        if org:
            qs = qs.filter(organization=org)

        notification = qs.first()
        if not notification:
            return JsonResponse({"error": "Notification not found or access denied"}, status=404)

        notification.delete()

        count_qs = Notification.objects.filter(user=request.user, is_read=False)
        if org:
            count_qs = count_qs.filter(organization=org)

        return JsonResponse({
            "status": "success",
            "id": pk,
            "unread_count": count_qs.count(),
        }, status=200)
