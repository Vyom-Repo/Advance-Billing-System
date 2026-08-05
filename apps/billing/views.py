"""apps/billing/views.py"""
from apps.common.views import ComingSoonView
from apps.common.mixins import BillingLoginRequiredMixin


class BillingComingSoon(BillingLoginRequiredMixin, ComingSoonView):
    module_name = "Invoices"
    module_description = "Create and manage GST invoices"
