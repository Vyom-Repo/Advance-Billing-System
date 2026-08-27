import logging
from django.contrib.auth.mixins import UserPassesTestMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse

logger = logging.getLogger(__name__)


class AdminRequiredMixin(UserPassesTestMixin):
    """
    Mixin enforcing that the current user is authenticated AND has staff or superuser privileges.
    Unauthenticated users are redirected to /admin-portal/login/.
    Authenticated non-staff users get an Access Denied message and are redirected to /admin-portal/login/.
    """

    def test_func(self) -> bool:
        user = self.request.user
        return user.is_authenticated and (user.is_staff or user.is_superuser)

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            logger.info("Unauthenticated access attempt to admin portal: %s", self.request.path)
            login_url = reverse("admin_portal:login")
            return redirect(f"{login_url}?next={self.request.path}")

        logger.warning("Unauthorized access attempt to admin portal by user: %s", self.request.user.email)
        messages.error(self.request, "Access Denied: Administrator privileges required.")
        return redirect("admin_portal:login")
