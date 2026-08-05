"""apps/organization/views.py"""
from apps.common.views import ComingSoonView
from apps.common.mixins import BillingLoginRequiredMixin


class OrganizationComingSoon(BillingLoginRequiredMixin, ComingSoonView):
    module_name = "Organization Settings"
    module_description = "Configure your business profile"
