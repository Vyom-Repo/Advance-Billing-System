"""apps/settings_app/views.py"""
from apps.common.views import ComingSoonView
from apps.common.mixins import BillingLoginRequiredMixin


class SettingsSettingsComingSoon(BillingLoginRequiredMixin, ComingSoonView):
    module_name = "Settings"
    module_description = "Application and account settings"
