import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import TemplateView, View
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from django.db.models import Q

from apps.common.mixins import PageTitleMixin
from apps.organization.models import Organization, PlanTier, UpgradeRequest, RequestStatus
from .mixins import AdminRequiredMixin

logger = logging.getLogger(__name__)


class AdminLoginView(PageTitleMixin, View):
    """
    Dedicated login view for the Advance Billing Admin Portal.
    Supports authenticating via username or email address.
    """
    page_title = "Admin Login — Advance Billing Portal"

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
            return redirect("admin_portal:dashboard")
        return render(request, "admin_portal/login.html", {"page_title": self.page_title})

    def post(self, request, *args, **kwargs):
        email_or_username = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")

        if not email_or_username or not password:
            messages.error(request, "Please provide both email/username and password.")
            return render(request, "admin_portal/login.html", {"page_title": self.page_title, "email": email_or_username})

        # 1. Try authenticating directly with email_or_username as username
        user = authenticate(request, username=email_or_username, password=password)

        # 2. If authentication failed, search by email address or username in User model
        if user is None:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user_obj = User.objects.get(Q(email__iexact=email_or_username) | Q(username__iexact=email_or_username))
                user = authenticate(request, username=user_obj.username, password=password)
            except (User.DoesNotExist, User.MultipleObjectsReturned):
                user = None

        if user is not None:
            if user.is_staff or user.is_superuser:
                login(request, user)
                logger.info("Admin login successful for: %s (%s)", user.username, user.email)
                next_url = request.GET.get("next") or request.POST.get("next")
                if next_url and next_url.startswith("/admin-portal"):
                    return redirect(next_url)
                return redirect("admin_portal:dashboard")
            else:
                logger.warning("Non-admin user attempted admin login: %s", user.email)
                messages.error(request, "Access Denied: This account does not have administrator privileges.")
                return render(request, "admin_portal/login.html", {"page_title": self.page_title, "email": email_or_username})
        else:
            messages.error(request, "Invalid username/email address or password.")
            return render(request, "admin_portal/login.html", {"page_title": self.page_title, "email": email_or_username})


class AdminLogoutView(View):
    """
    Logs out admin user and redirects to admin login.
    """
    def get(self, request, *args, **kwargs):
        logout(request)
        messages.info(request, "You have been logged out of the Admin Portal.")
        return redirect("admin_portal:login")

    def post(self, request, *args, **kwargs):
        logout(request)
        messages.info(request, "You have been logged out of the Admin Portal.")
        return redirect("admin_portal:login")


class AdminDashboardView(AdminRequiredMixin, PageTitleMixin, TemplateView):
    """
    Main Admin Dashboard displaying upgrade requests, status KPIs, and controls.
    """
    template_name = "admin_portal/dashboard.html"
    page_title = "Admin Dashboard — Advance Billing Portal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        status_filter = self.request.GET.get("status", "all").lower().strip()
        search_query = self.request.GET.get("q", "").strip()

        qs = UpgradeRequest.objects.select_related("organization", "user", "approved_by").all()

        # Summary KPIs
        context["pending_count"] = UpgradeRequest.objects.filter(status=RequestStatus.PENDING).count()
        context["approved_count"] = UpgradeRequest.objects.filter(status=RequestStatus.APPROVED).count()
        context["rejected_count"] = UpgradeRequest.objects.filter(status=RequestStatus.REJECTED).count()
        context["total_count"] = UpgradeRequest.objects.count()

        # Filtering by status
        if status_filter in [RequestStatus.PENDING, RequestStatus.APPROVED, RequestStatus.REJECTED]:
            qs = qs.filter(status=status_filter)

        # Filtering by search query
        if search_query:
            qs = qs.filter(
                Q(requester_name__icontains=search_query) |
                Q(requester_email__icontains=search_query) |
                Q(organization__business_name__icontains=search_query)
            )

        context["upgrade_requests"] = qs
        context["status_filter"] = status_filter
        context["search_query"] = search_query
        return context


class AdminApproveRequestView(AdminRequiredMixin, View):
    """
    Handles approving an upgrade request:
    1. Sets Organization.plan = 'paid'
    2. Sets UpgradeRequest.status = 'approved', approved_at = now, approved_by = admin
    """
    def post(self, request, pk, *args, **kwargs):
        upgrade_request = get_object_or_404(UpgradeRequest, pk=pk)
        org = upgrade_request.organization

        admin_note = request.POST.get("admin_note", "").strip()

        # 1. Upgrade organization plan to PAID (this automatically removes watermark)
        org.plan = PlanTier.PAID
        org.save(update_fields=["plan", "updated_at"])

        # 2. Update UpgradeRequest record
        upgrade_request.status = RequestStatus.APPROVED
        upgrade_request.approved_at = timezone.now()
        upgrade_request.approved_by = request.user
        if admin_note:
            upgrade_request.admin_note = admin_note
        upgrade_request.save()

        logger.info(
            "Upgrade request %s approved by admin %s for organization %s",
            pk, request.user.email, org.business_name
        )

        messages.success(
            request,
            f"Upgrade approved successfully! Watermark has been removed for '{org.business_name}'."
        )
        return redirect("admin_portal:dashboard")


class AdminRejectRequestView(AdminRequiredMixin, View):
    """
    Handles rejecting an upgrade request.
    """
    def post(self, request, pk, *args, **kwargs):
        upgrade_request = get_object_or_404(UpgradeRequest, pk=pk)
        admin_note = request.POST.get("admin_note", "").strip()

        upgrade_request.status = RequestStatus.REJECTED
        if admin_note:
            upgrade_request.admin_note = admin_note
        upgrade_request.save()

        logger.info(
            "Upgrade request %s rejected by admin %s for organization %s",
            pk, request.user.email, upgrade_request.organization.business_name
        )

        messages.info(
            request,
            f"Upgrade request for '{upgrade_request.organization.business_name}' has been marked as rejected."
        )
        return redirect("admin_portal:dashboard")


class SmtpDiagnosticView(AdminRequiredMixin, View):
    """
    TEMPORARY production diagnostic view to test DNS resolution and TCP socket
    reachability to Brevo SMTP servers (smtp-relay.brevo.com:587, 2525, 465).
    Requires authenticated staff/superuser access. Exposes zero credentials.
    """
    def get(self, request, *args, **kwargs):
        import socket
        import time
        from django.http import JsonResponse

        target_host = "smtp-relay.brevo.com"
        results = {
            "target": target_host,
            "dns": {},
            "port_587": {},
            "port_2525": {},
            "port_465": {},
        }

        # 1. Test DNS Resolution
        t0 = time.perf_counter()
        try:
            hostname, aliases, ip_list = socket.gethostbyname_ex(target_host)
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            results["dns"] = {
                "success": True,
                "hostname": hostname,
                "ips": ip_list,
                "elapsed_ms": elapsed_ms,
                "error": None,
            }
            logger.info("SMTP DIAGNOSTIC: DNS resolution succeeded (IPs: %s, Elapsed: %sms)", ip_list, elapsed_ms)
        except Exception as e:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            results["dns"] = {
                "success": False,
                "ips": [],
                "elapsed_ms": elapsed_ms,
                "error": f"{type(e).__name__}: {str(e)}",
            }
            logger.error("SMTP DIAGNOSTIC: DNS resolution failed: %s: %s", type(e).__name__, str(e))

        # Helper for TCP socket connectivity test
        def _test_tcp_port(port: int) -> dict:
            t_start = time.perf_counter()
            try:
                with socket.create_connection((target_host, port), timeout=10.0):
                    elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
                    logger.info("SMTP DIAGNOSTIC: TCP %s reachable (Elapsed: %sms)", port, elapsed_ms)
                    return {
                        "success": True,
                        "elapsed_ms": elapsed_ms,
                        "error": None,
                    }
            except Exception as e:
                elapsed_ms = round((time.perf_counter() - t_start) * 1000, 2)
                err_msg = f"{type(e).__name__}: {str(e)}"
                logger.error("SMTP DIAGNOSTIC: TCP %s unreachable: %s", port, err_msg)
                return {
                    "success": False,
                    "elapsed_ms": elapsed_ms,
                    "error": err_msg,
                }

        # 2. Test TCP 587
        results["port_587"] = _test_tcp_port(587)

        # 3. Test TCP 2525
        results["port_2525"] = _test_tcp_port(2525)

        # 4. Test TCP 465
        results["port_465"] = _test_tcp_port(465)

        return JsonResponse(results)
