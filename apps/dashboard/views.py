import datetime
import logging
from decimal import Decimal
from typing import Any

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from apps.billing.models import Invoice, InvoiceStatus
from apps.common.mixins import BillingLoginRequiredMixin, PageTitleMixin
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
class DashboardView(BillingLoginRequiredMixin, PageTitleMixin, TemplateView):
    """
    Main application dashboard rendering real organization stats,
    recent invoices, revenue trend charts, and quick actions.
    """
    template_name = "dashboard/index.html"
    page_title = "Dashboard — Advance Billing"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Fetch organization
        user_org = getattr(user, "organization", None)
        if not user_org:
            user_org = Organization.objects.filter(owner=user).first()

        # Currency Preference
        curr_code = "INR"
        if hasattr(user, "invoice_preference") and user.invoice_preference.default_currency:
            curr_code = user.invoice_preference.default_currency

        curr_symbol_map = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}
        curr_icon_map = {"INR": "indian-rupee", "USD": "dollar-sign", "EUR": "euro", "GBP": "pound-sterling"}
        currency_symbol = curr_symbol_map.get(curr_code, "₹")
        currency_icon = curr_icon_map.get(curr_code, "indian-rupee")

        context["currency_code"] = curr_code
        context["currency_symbol"] = currency_symbol
        context["currency_icon"] = currency_icon

        if user_org:
            invoices = Invoice.objects.filter(organization=user_org)
            issued_invoices = invoices.filter(status=InvoiceStatus.ISSUED)

            # Revenue totals
            total_revenue = issued_invoices.aggregate(tot=Sum("grand_total"))["tot"] or Decimal("0.00")

            today = timezone.now().date()
            curr_month_invoices = issued_invoices.filter(
                invoice_date__year=today.year, invoice_date__month=today.month
            )
            monthly_revenue = curr_month_invoices.aggregate(tot=Sum("grand_total"))["tot"] or Decimal("0.00")

            # MoM Growth
            if today.month == 1:
                prev_year = today.year - 1
                prev_month = 12
            else:
                prev_year = today.year
                prev_month = today.month - 1

            prev_month_invoices = issued_invoices.filter(
                invoice_date__year=prev_year, invoice_date__month=prev_month
            )
            prev_monthly_revenue = prev_month_invoices.aggregate(tot=Sum("grand_total"))["tot"] or Decimal("0.00")

            if prev_monthly_revenue > Decimal("0.00"):
                growth_pct = round(((monthly_revenue - prev_monthly_revenue) / prev_monthly_revenue) * 100)
                if growth_pct > 0:
                    growth_status = "positive"
                    growth_text = f"↑ {growth_pct}% from last month"
                elif growth_pct < 0:
                    growth_status = "negative"
                    growth_text = f"↓ {abs(growth_pct)}% from last month"
                else:
                    growth_status = "neutral"
                    growth_text = "0% from last month"
            else:
                growth_status = "neutral"
                growth_text = "No previous data"

            total_invoices_count = invoices.count()
            total_customers_count = Customer.objects.filter(organization=user_org).count()
            total_products_count = Product.objects.filter(organization=user_org).count()

            # Rolling 6-month chart
            chart_labels = []
            chart_values = []
            for i in range(5, -1, -1):
                m = today.month - i
                y = today.year
                while m <= 0:
                    m += 12
                    y -= 1
                month_date = datetime.date(y, m, 1)
                label = month_date.strftime("%b")
                m_rev = (
                    issued_invoices.filter(invoice_date__year=y, invoice_date__month=m).aggregate(
                        tot=Sum("grand_total")
                    )["tot"]
                    or Decimal("0.00")
                )
                chart_labels.append(label)
                chart_values.append(float(m_rev))

            recent_invoices_qs = invoices.select_related("customer").order_by("-created_at")[:5]

        else:
            total_revenue = Decimal("0.00")
            monthly_revenue = Decimal("0.00")
            growth_status = "neutral"
            growth_text = "No previous data"
            total_invoices_count = 0
            total_customers_count = 0
            total_products_count = 0
            chart_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
            chart_values = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
            recent_invoices_qs = []

        context["stats"] = {
            "total_revenue": total_revenue,
            "monthly_revenue": monthly_revenue,
            "growth_status": growth_status,
            "growth_text": growth_text,
            "total_customers": total_customers_count,
            "total_products": total_products_count,
            "total_invoices": total_invoices_count,
        }

        context["chart_labels"] = chart_labels
        context["chart_values"] = chart_values
        context["recent_invoices"] = recent_invoices_qs

        context["quick_actions"] = [
            {
                "label": "New Invoice",
                "url": reverse("billing:create"),
                "icon": "file-plus",
                "desc": "Create and issue a GST invoice",
            },
            {
                "label": "Add Customer",
                "url": reverse("customers:create"),
                "icon": "user-plus",
                "desc": "Register a new client or business",
            },
            {
                "label": "Add Product",
                "url": reverse("products:create"),
                "icon": "package-plus",
                "desc": "Add goods or service items",
            },
        ]
        return context

