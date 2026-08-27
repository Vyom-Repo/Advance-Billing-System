import logging
from django.shortcuts import redirect
from django.views import View
from django.contrib import messages
from django.contrib.auth import login, logout

from .services import DemoService

logger = logging.getLogger(__name__)


class DemoEntryView(View):
    """
    Public entry point for the disposable interactive live demo (/demo/).
    Creates a brand-new, isolated temporary demo tenant and authenticates the visitor.
    """
    def get(self, request, *args, **kwargs):
        # 1. If visitor is already in a demo session, purge old session first
        old_session_id = request.session.get("demo_session_id")
        if old_session_id and request.user.is_authenticated:
            org = getattr(request.user, "organization", None)
            user = request.user
            if org and org.is_demo:
                logout(request)
                DemoService.destroy_demo_session(org, user)

        # 2. Run light-weight cleanup of expired abandoned demo sessions (>2 hours old)
        try:
            DemoService.cleanup_expired_demo_sessions(max_age_hours=2)
        except Exception as e:
            logger.error("Error during abandoned demo session cleanup: %s", e)

        # 3. Create fresh isolated demo session (new User, new Org, new sample data)
        user, org, session_id = DemoService.create_isolated_demo_session()

        # 4. Authenticate visitor into the temporary user session
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        request.session["is_demo_mode"] = True
        request.session["demo_session_id"] = session_id

        logger.info("Visitor entered new isolated demo session %s", session_id)
        messages.success(
            request,
            "Welcome to the Advance Billing Live Demo! You are exploring a fresh, isolated demo environment."
        )
        return redirect("dashboard:index")


class DemoResetView(View):
    """
    Resets the current temporary demo environment back to its default clean sample state (/demo/reset/).
    """
    def get(self, request, *args, **kwargs):
        return self._reset(request)

    def post(self, request, *args, **kwargs):
        return self._reset(request)

    def _reset(self, request):
        if not request.session.get("is_demo_mode") or not request.user.is_authenticated:
            messages.error(request, "Reset is only available in Demo Mode.")
            return redirect("dashboard:index")

        org = getattr(request.user, "organization", None)
        if not org or not org.is_demo:
            messages.error(request, "Reset is only available in Demo Mode.")
            return redirect("dashboard:index")

        DemoService.reset_demo_data(org, request.user)

        messages.success(request, "Demo environment has been reset to its default clean sample state.")
        return redirect("dashboard:index")


class DemoExitView(View):
    """
    Exits demo mode (/demo/exit/).
    Destroys the temporary demo tenant (User, Org, Invoices, Customers, Products) completely from the database.
    """
    def get(self, request, *args, **kwargs):
        return self._exit(request)

    def post(self, request, *args, **kwargs):
        return self._exit(request)

    def _exit(self, request):
        demo_session_id = request.session.get("demo_session_id")
        is_demo_mode = request.session.get("is_demo_mode")

        if not is_demo_mode or not request.user.is_authenticated:
            logout(request)
            return redirect("landing")

        org = getattr(request.user, "organization", None)
        user = request.user

        # Verify session ownership & is_demo flag before destructive deletion
        if org and getattr(org, "is_demo", False) and org.demo_session_id == demo_session_id:
            # 1. Logout and flush session cleanly FIRST
            logout(request)

            # 2. Execute explicit atomic DB deletion of temporary org & user AFTER logout
            DemoService.destroy_demo_session(org, user)
        else:
            # Not a demo org — just logout cleanly without deleting
            logout(request)

        messages.info(request, "You have exited the demo environment.")
        return redirect("landing")
