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
