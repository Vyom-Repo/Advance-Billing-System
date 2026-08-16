"""
apps/dashboard/views.py

Advance Billing — Dashboard View
"""
import logging
from typing import Any

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from apps.common.mixins import BillingLoginRequiredMixin, PageTitleMixin

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
class DashboardView(BillingLoginRequiredMixin, PageTitleMixin, TemplateView):
    """
    Main application dashboard.
    In Phase 1: renders with placeholder/static data.
    In later phases: real data from customers, invoices, and billing modules.
    """
    template_name = "dashboard/index.html"
    page_title = "Dashboard — Advance Billing"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)

        # Placeholder data — will be replaced with real queries in later phases
        context["stats"] = {
            "total_revenue": 0,
            "monthly_revenue": 0,
            "total_customers": 0,
            "total_products": 0,
            "total_invoices": 0,
        }
        context["recent_invoices"] = []
        context["quick_actions"] = [
            {"label": "New Invoice", "url": "/invoices/create/", "icon": "file-plus"},
            {"label": "Add Customer", "url": "/customers/create/", "icon": "user-plus"},
            {"label": "Add Product", "url": "/products/create/", "icon": "package-plus"},
        ]
        return context
