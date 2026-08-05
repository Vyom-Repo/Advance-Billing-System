"""
apps/common/mixins.py

Advance Billing — Reusable View Mixins
========================================
Provides reusable mixins that extend Django's built-in class-based view mixins.
"""

import logging
from typing import Any

from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


class BillingLoginRequiredMixin(LoginRequiredMixin):
    """
    Extended LoginRequiredMixin for Advance Billing views.

    Adds:
      - Consistent redirect to /login/
      - Logging of unauthenticated access attempts
    """

    login_url = "/login/"
    redirect_field_name = "next"

    def handle_no_permission(self) -> HttpResponse:
        logger.info(
            "Unauthenticated access attempt to: %s",
            self.request.path,  # type: ignore[attr-defined]
        )
        return super().handle_no_permission()


class PageTitleMixin:
    """
    Mixin that injects a page title into the template context.

    Usage:
        class MyView(PageTitleMixin, TemplateView):
            page_title = "My Page"
    """

    page_title: str = "Advance Billing"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)  # type: ignore[misc]
        context["page_title"] = self.page_title
        return context
