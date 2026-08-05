"""apps/customers/views.py"""
from apps.common.views import ComingSoonView
from apps.common.mixins import BillingLoginRequiredMixin


class CustomersComingSoon(BillingLoginRequiredMixin, ComingSoonView):
    module_name = "Customers"
    module_description = "Manage your GST customers"
