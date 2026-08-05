"""apps/products/views.py"""
from apps.common.views import ComingSoonView
from apps.common.mixins import BillingLoginRequiredMixin


class ProductsComingSoon(BillingLoginRequiredMixin, ComingSoonView):
    module_name = "Products & Services"
    module_description = "Manage products, services, HSN/SAC codes"
