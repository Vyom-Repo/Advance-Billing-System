"""apps/settings_app/views.py"""
from django.views.generic import UpdateView, FormView, TemplateView, View
from django.contrib.auth.views import PasswordChangeView
from django.contrib import messages
from django.urls import reverse_lazy
from django.shortcuts import redirect
import sys
import django
from django.conf import settings

from apps.common.mixins import BillingLoginRequiredMixin, PageTitleMixin
from .forms import UserProfileForm, SettingsPasswordChangeForm, InvoicePreferenceForm, DocumentPreferenceForm
from .models import UserPreference, InvoicePreference, DocumentPreference


class SettingsProfileView(BillingLoginRequiredMixin, PageTitleMixin, UpdateView):
    template_name = "settings_app/profile.html"
    form_class = UserProfileForm
    success_url = reverse_lazy("settings_app:profile")
    page_title = "Profile Settings — Advance Billing"
    
    def get_object(self, queryset=None):
        return self.request.user
        
    def form_valid(self, form):
        messages.success(self.request, "Profile updated successfully.")
        return super().form_valid(form)

class SettingsChangeEmailView(BillingLoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        new_email = request.POST.get('new_email', '').strip()
        
        if not new_email:
            messages.error(request, "Please provide a valid email address.")
            return redirect("settings_app:profile")
            
        if new_email == request.user.email:
            messages.info(request, "This is already your current email address.")
            return redirect("settings_app:profile")
            
        # Check if email is already in use by another user
        from django.contrib.auth import get_user_model
        User = get_user_model()
        if User.objects.filter(email=new_email).exclude(pk=request.user.pk).exists():
            messages.error(request, "This email address is already registered to another account.")
            return redirect("settings_app:profile")
            
        otp_code = get_random_string(length=6, allowed_chars='0123456789')
        request.session['profile_otp'] = otp_code
        request.session['pending_email'] = new_email
        
        # Send OTP to new email
        dummy_user = User(email=new_email, first_name=request.user.first_name)
        EmailService.send_otp_email(dummy_user, otp_code)
        
        return redirect("settings_app:profile_verify")

class SettingsProfileVerifyView(BillingLoginRequiredMixin, PageTitleMixin, TemplateView):
    template_name = "settings_app/profile_verify.html"
    page_title = "Verify Email Change — Advance Billing"
    
    def get(self, request, *args, **kwargs):
        if 'profile_otp' not in request.session:
            messages.error(request, "OTP session expired or invalid. Please try again.")
            return redirect("settings_app:profile")
        return super().get(request, *args, **kwargs)
        
    def post(self, request, *args, **kwargs):
        if 'profile_otp' not in request.session:
            messages.error(request, "OTP session expired. Please start over.")
            return redirect("settings_app:profile")
            
        entered_otp = request.POST.get("otp_code", "").strip()
        expected_otp = request.session.get('profile_otp')
        
        if entered_otp == expected_otp:
            # Success: update email
            new_email = request.session.get('pending_email')
            user = request.user
            user.email = new_email
            user.save()
            
            # Clean up session
            del request.session['profile_otp']
            del request.session['pending_email']
            
            messages.success(request, "Email address updated successfully.")
            return redirect("settings_app:profile")
        else:
            messages.error(request, "Invalid OTP code. Please try again.")
            return self.get(request, *args, **kwargs)


from django.utils.crypto import get_random_string
from django.contrib.auth import update_session_auth_hash
from apps.common.services.email_service import EmailService

class SettingsSecurityView(BillingLoginRequiredMixin, PageTitleMixin, PasswordChangeView):
    template_name = "settings_app/security.html"
    form_class = SettingsPasswordChangeForm
    page_title = "Security Settings — Advance Billing"
    
    def form_valid(self, form):
        # Generate OTP
        otp_code = get_random_string(length=6, allowed_chars='0123456789')
        
        # Save to session (server-side, secure)
        self.request.session['security_otp'] = otp_code
        self.request.session['pending_password'] = form.cleaned_data['new_password1']
        
        # Send Email
        EmailService.send_otp_email(self.request.user, otp_code)
        
        return redirect("settings_app:security_verify")

class SettingsSecurityVerifyView(BillingLoginRequiredMixin, PageTitleMixin, TemplateView):
    template_name = "settings_app/security_verify.html"
    page_title = "Verify Password Change — Advance Billing"
    
    def get(self, request, *args, **kwargs):
        if 'security_otp' not in request.session:
            messages.error(request, "OTP session expired or invalid. Please try again.")
            return redirect("settings_app:security")
        return super().get(request, *args, **kwargs)
        
    def post(self, request, *args, **kwargs):
        if 'security_otp' not in request.session:
            messages.error(request, "OTP session expired. Please start over.")
            return redirect("settings_app:security")
            
        entered_otp = request.POST.get("otp_code", "").strip()
        expected_otp = request.session.get('security_otp')
        
        if entered_otp == expected_otp:
            # Success: update password
            new_password = request.session.get('pending_password')
            user = request.user
            user.set_password(new_password)
            user.save()
            
            # Keep user logged in
            update_session_auth_hash(request, user)
            
            # Clean up session
            del request.session['security_otp']
            del request.session['pending_password']
            
            messages.success(request, "Password updated successfully.")
            return redirect("settings_app:security")
        else:
            messages.error(request, "Invalid OTP code. Please try again.")
            return self.get(request, *args, **kwargs)


class SettingsAppearanceView(BillingLoginRequiredMixin, PageTitleMixin, TemplateView):
    template_name = "settings_app/appearance.html"
    page_title = "Appearance Settings — Advance Billing"

    def post(self, request, *args, **kwargs):
        theme_id = request.POST.get("theme_id")
        available_themes = [t["id"] for t in settings.AVAILABLE_THEMES]
        
        if theme_id in available_themes:
            # Save to Database
            preference, created = UserPreference.objects.get_or_create(user=request.user)
            preference.theme = theme_id
            preference.save()
            
            # Also save to session for immediate feedback
            request.session["theme"] = theme_id
            messages.success(request, "Theme updated successfully.")
        else:
            messages.error(request, "Invalid theme selected.")
            
        return redirect("settings_app:appearance")


class SettingsSystemView(BillingLoginRequiredMixin, PageTitleMixin, TemplateView):
    template_name = "settings_app/system.html"
    page_title = "System Information — Advance Billing"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Determine database type
        db_engine = settings.DATABASES.get('default', {}).get('ENGINE', '')
        if 'postgresql' in db_engine:
            db_type = 'PostgreSQL'
        elif 'sqlite' in db_engine:
            db_type = 'SQLite'
        else:
            db_type = 'Unknown'

        # Get Organization if exists
        org_name = "None"
        try:
            from apps.organization.models import Organization
            org = getattr(self.request.user, "organization", None)
            if not org:
                org = Organization.objects.filter(owner=self.request.user).first()
            if org:
                org_name = org.business_name
        except Exception:
            pass

        context.update({
            'app_version': getattr(settings, 'APP_VERSION', '1.0.0'),
            'django_env': getattr(settings, 'DJANGO_ENV', 'production').title(),
            'time_zone': getattr(settings, 'TIME_ZONE', 'UTC'),
            'logged_user': self.request.user.email,
            'is_verified': self.request.user.is_active,
            'org_name': org_name,
            'date_joined': self.request.user.date_joined,
            'last_login': self.request.user.last_login,
            'current_plan': 'Starter',
            'org_status': 'Active' if org_name != "None" else 'Pending Setup'
        })
        return context

class SettingsNotificationsView(BillingLoginRequiredMixin, PageTitleMixin, TemplateView):
    template_name = "settings_app/notifications.html"
    page_title = "Notifications — Advance Billing"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        from apps.common.models import Notification  # noqa: PLC0415
        from django.utils import timezone  # noqa: PLC0415
        from django.utils.timesince import timesince  # noqa: PLC0415
        
        now = timezone.now()
        today_date = now.date()
        yesterday_date = today_date - timezone.timedelta(days=1)
        
        org = getattr(self.request.user, "organization", None)
        if not org:
            from apps.organization.models import Organization  # noqa: PLC0415
            org = Organization.objects.filter(owner=self.request.user).first()

        qs = Notification.objects.filter(user=self.request.user)
        if org:
            qs = qs.filter(organization=org)

        db_notifications = qs.order_by('-created_at')
        
        notifications = []
        for n in db_notifications:
            # Determine group
            created_date = n.created_at.date()
            if created_date == today_date:
                group = "Today"
                time_str = f"{timesince(n.created_at).split(',')[0]} ago"
                if time_str == "0 minutes ago":
                    time_str = "Just now"
            elif created_date == yesterday_date:
                group = "Yesterday"
                time_str = n.created_at.strftime("Yesterday %I:%M %p")
            else:
                group = "Earlier"
                time_str = n.created_at.strftime("%b %d").replace(" 0", " ")
                
            # Assign colors based on category & event_type icon
            icon = n.get_icon_name() or "bell"
            if n.category == "billing":
                icon_color = "var(--color-success)"
                icon_bg = "var(--color-success-bg)"
            elif n.category == "customers":
                icon_color = "var(--color-info)"
                icon_bg = "var(--color-info-bg)"
            elif n.category == "organization":
                icon_color = "var(--color-text-secondary)"
                icon_bg = "var(--color-bg-raised)"
            elif n.category == "security":
                icon_color = "var(--color-warning)"
                icon_bg = "var(--color-warning-bg)"
            elif n.category == "settings":
                icon_color = "var(--color-text-secondary)"
                icon_bg = "var(--color-bg-raised)"
            else:
                icon_color = "var(--color-accent)"
                icon_bg = "var(--color-accent-subtle)"
                
            target_url = n.get_target_url()

            notifications.append({
                "id": str(n.id),
                "pk": n.id,
                "title": n.title,
                "desc": n.message,
                "message": n.message,
                "category": n.category,
                "icon": icon,
                "icon_color": icon_color,
                "icon_bg": icon_bg,
                "is_read": n.is_read,
                "group": group,
                "time": time_str,
                "action_url": target_url or "#",
                "target_url": target_url or "",
            })
            
        context['notifications_list'] = notifications
        return context

class SettingsInvoicePreferencesView(BillingLoginRequiredMixin, PageTitleMixin, UpdateView):
    template_name = "settings_app/invoice_preferences.html"
    form_class = InvoicePreferenceForm
    success_url = reverse_lazy("settings_app:invoice_preferences")
    page_title = "Invoice Preferences — Advance Billing"
    
    def get_object(self, queryset=None):
        obj, created = InvoicePreference.objects.get_or_create(user=self.request.user)
        return obj
        
    def form_valid(self, form):
        messages.success(self.request, "Invoice preferences updated successfully.")
        return super().form_valid(form)

from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
import json
try:
    from weasyprint import HTML
except ImportError:
    HTML = None



class SettingsInvoiceDesignView(BillingLoginRequiredMixin, PageTitleMixin, UpdateView):
    template_name = "settings_app/invoice_design.html"
    form_class = DocumentPreferenceForm
    success_url = reverse_lazy("settings_app:invoice_design")
    page_title = "Invoice Design — Advance Billing"
    
    def get_object(self, queryset=None):
        obj, created = DocumentPreference.objects.get_or_create(user=self.request.user)
        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from apps.common.services.organization_service import OrganizationService
        org_data = OrganizationService.get_company_assets(self.request.user)
        
        has_logo = False
        has_letterhead = False
        has_signature = False
        has_bank = False
        has_qr = False
        has_terms = False
        
        if org_data:
            has_logo = bool(org_data.get("logo"))
            has_letterhead = bool(org_data.get("letterhead"))
            sig_mode = org_data.get("signature_mode") or "none"
            if sig_mode == "image":
                has_signature = bool(org_data.get("signature"))
            elif sig_mode == "authorized_signatory":
                has_signature = bool((org_data.get("authorized_signatory_name") or "").strip())
            else:
                has_signature = False
            has_bank = bool(org_data.get("default_bank"))
            has_qr = bool(org_data.get("qr_code"))
            has_terms = bool((org_data.get("terms_and_conditions") or "").strip())
            
        context['has_logo'] = has_logo
        context['has_letterhead'] = has_letterhead
        context['has_signature'] = has_signature
        context['has_bank'] = has_bank
        context['has_qr'] = has_qr
        context['has_terms'] = has_terms

        TEMPLATE_DISPLAY_NAMES = {
            'gst_classic': 'GST Classic',
            'flipkart_invoice': 'Flipkart Invoice',
            'retail_gst_compact': 'Retail GST Compact',
            'evergreen': 'Evergreen',
            'compact_template': 'Compact',
            'genz': 'GenZ',
            'landscape_template': 'Landscape',
            'modern_template': 'Modern',
            'mrp_discount_template': 'MRP + Discount',
            'professional_template': 'Professional',
            'service_template': 'Service',
            'vintage': 'Vintage',
        }
        obj = self.get_object()
        context['active_template_title'] = TEMPLATE_DISPLAY_NAMES.get(
            obj.template_name, obj.template_name
        )
        
        # Get available reference templates
        import os
        from django.conf import settings
        reference_dir = os.path.join(settings.BASE_DIR, 'templates', 'reference')
        available_references = []
        if os.path.exists(reference_dir):
            for f in os.listdir(reference_dir):
                if f.endswith('.html'):
                    available_references.append(f.replace('.html', ''))
        context['available_references'] = json.dumps(available_references)
        
        return context
        
    def form_valid(self, form):
        # Set onboarding completed to True after any save
        form.instance.onboarding_completed = True
        form.instance.save()
        messages.success(self.request, "Invoice design preferences saved successfully.")
        return super().form_valid(form)

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from apps.billing.services.pdf_resource_guard import PDFCapacityExceededError

@method_decorator(ratelimit(key="user_or_ip", rate="30/m", block=False), name="post")
class SettingsInvoiceDesignPreviewAPIView(BillingLoginRequiredMixin, View):
    """
    Renders a PDF preview using the unified render_bill_pdf pipeline.

    Accepts a JSON body with any DocumentPreference fields plus an optional
    ``template_name`` key.  The posted values are treated as one-off
    request_overrides — they are NOT saved to the database.
    """
    def post(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            return JsonResponse(
                {"error": "Rate limit exceeded. Please wait before making more preview requests."},
                status=429,
            )

        try:
            from apps.invoices.services.invoice_preview_service import InvoicePreviewService
            from apps.invoices.services.bill_serializer import serialize_bill_for_render
            from apps.common.services.sample_data_service import SampleDataService
            from apps.common.services.organization_service import OrganizationService
            from apps.common.services.layout_engine import PrintableFrameBuilder
            import os

            data = json.loads(request.body)

            # Resolve config (template defaults + user prefs + request body as overrides)
            config = InvoicePreviewService.resolve_render_config(
                user=request.user,
                request_overrides=data,
            )
            template_path = InvoicePreviewService.resolve_template_path(config.get("template_name"))

            # Build org / company data
            org_data = OrganizationService.get_company_assets(request.user)
            if org_data:
                org_obj = org_data["organization"]
                logo = org_data.get("logo")
                sig = org_data.get("signature")
                lh = org_data.get("letterhead")
                company = {
                    "name": org_data["business_name"],
                    "address": f"{org_data['address_line_1']} {org_data['address_line_2']}".strip(),
                    "city": org_data["city"],
                    "state": org_data["state"],
                    "gstin": org_data["gstin"],
                    "email": org_data["email"],
                    "phone": org_data["phone"],
                    "logo_url": f"file://{logo.path}" if logo and hasattr(logo, "path") and os.path.exists(logo.path) else None,
                    "signature_url": f"file://{sig.path}" if sig and hasattr(sig, "path") and os.path.exists(sig.path) else None,
                    "letterhead_url": f"file://{lh.path}" if lh and hasattr(lh, "path") and os.path.exists(lh.path) else None,
                    "signature_mode": org_data.get("signature_mode") or "none",
                    "authorized_signatory_name": org_data.get("authorized_signatory_name") or "",
                    "show_computer_generated_disclaimer": org_data.get("show_computer_generated_disclaimer", False),
                }
                if org_data.get("default_bank"):
                    company["bank_name"] = org_data["default_bank"].bank_name
                    company["acc_no"]    = org_data["default_bank"].account_number
                    company["ifsc"]      = org_data["default_bank"].ifsc_code
                    company["branch"]    = getattr(org_data["default_bank"], "branch_name", "")
            else:
                org_obj = None
                company = SampleDataService.sample_company()

            invoice  = SampleDataService.sample_invoice(request.user)
            customer = SampleDataService.sample_customer()
            items    = SampleDataService.sample_items()

            bill_data  = serialize_bill_for_render(invoice, customer, items, company, org_obj)
            layout_frame = PrintableFrameBuilder.build_frame(org_obj, config)

            pdf_bytes = InvoicePreviewService.render_bill_pdf(
                bill_data=bill_data,
                config=config,
                template_file_path=template_path,
                layout_frame=layout_frame,
                org=org_obj,
            )
            return HttpResponse(pdf_bytes, content_type="application/pdf")

        except PDFCapacityExceededError:
            return JsonResponse(
                {"error": "PDF preview capacity is temporarily busy. Please retry in a moment."},
                status=503,
            )
        except Exception as e:
            import traceback
            return HttpResponse(
                f"<div style='color:red;padding:20px;'>Error rendering preview: {e}<br><pre>{traceback.format_exc()}</pre></div>",
                status=400,
            )

@method_decorator(ratelimit(key="user_or_ip", rate="15/m", block=False), name="get")
class SettingsInvoiceDesignDownloadView(BillingLoginRequiredMixin, View):
    """
    Generates a PDF download using the user's saved DocumentPreference settings.
    Supports query parameters e.g. ?letterhead=true or ?print_on_letterhead=1.
    Uses the unified render_bill_pdf pipeline with automatic fallback.
    """
    def get(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            return HttpResponse(
                "Rate limit exceeded. Please wait before making more PDF requests.",
                status=429,
                content_type="text/plain",
            )

        if not HTML:
            return HttpResponse("WeasyPrint is not installed or configured correctly.", status=500)

        from apps.invoices.services.invoice_preview_service import InvoicePreviewService
        from apps.invoices.services.bill_serializer import serialize_bill_for_render
        from apps.common.services.sample_data_service import SampleDataService
        from apps.common.services.organization_service import OrganizationService
        from apps.common.services.layout_engine import PrintableFrameBuilder
        from apps.settings_app.models import DocumentPreference
        import os

        # Check for letterhead or template_name GET parameter overrides
        request_overrides = {}
        lh_param = request.GET.get("letterhead") or request.GET.get("print_on_letterhead")
        if lh_param is not None:
            request_overrides["print_on_letterhead"] = lh_param.lower() in ("true", "1", "yes", "on")

        tpl_param = request.GET.get("template_name")
        if tpl_param:
            request_overrides["template_name"] = tpl_param

        config = InvoicePreviewService.resolve_render_config(
            user=request.user,
            request_overrides=request_overrides if request_overrides else None,
        )
        template_path = InvoicePreviewService.resolve_template_path(config.get("template_name"))

        org_data = OrganizationService.get_company_assets(request.user)
        if org_data:
            org_obj = org_data["organization"]
            logo = org_data.get("logo")
            sig = org_data.get("signature")
            lh = org_data.get("letterhead")
            company = {
                "name": org_data["business_name"],
                "address": f"{org_data['address_line_1']} {org_data['address_line_2']}".strip(),
                "city": org_data["city"],
                "state": org_data["state"],
                "gstin": org_data["gstin"],
                "email": org_data["email"],
                "phone": org_data["phone"],
                "logo_url": f"file://{logo.path}" if logo and hasattr(logo, "path") and os.path.exists(logo.path) else None,
                "signature_url": f"file://{sig.path}" if sig and hasattr(sig, "path") and os.path.exists(sig.path) else None,
                "letterhead_url": f"file://{lh.path}" if lh and hasattr(lh, "path") and os.path.exists(lh.path) else None,
                "signature_mode": org_data.get("signature_mode") or "none",
                "authorized_signatory_name": org_data.get("authorized_signatory_name") or "",
                "show_computer_generated_disclaimer": org_data.get("show_computer_generated_disclaimer", False),
            }
            if org_data.get("default_bank"):
                company["bank_name"] = org_data["default_bank"].bank_name
                company["acc_no"]    = org_data["default_bank"].account_number
                company["ifsc"]      = org_data["default_bank"].ifsc_code
                company["branch"]    = getattr(org_data["default_bank"], "branch_name", "")
        else:
            org_obj = None
            company = SampleDataService.sample_company()

        invoice  = SampleDataService.sample_invoice(request.user)
        customer = SampleDataService.sample_customer()
        items    = SampleDataService.sample_items()

        bill_data    = serialize_bill_for_render(invoice, customer, items, company, org_obj)
        layout_frame = PrintableFrameBuilder.build_frame(org_obj, config)

        try:
            pdf_bytes = InvoicePreviewService.render_bill_pdf(
                bill_data=bill_data,
                config=config,
                template_file_path=template_path,
                layout_frame=layout_frame,
                org=org_obj,
            )
        except PDFCapacityExceededError:
            return HttpResponse(
                "PDF rendering capacity is temporarily busy. Please try again in a moment.",
                status=503,
                content_type="text/plain",
            )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = f"Invoice_{bill_data.get('bill', {}).get('number', 'Document')}.pdf"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

from django.template.exceptions import TemplateDoesNotExist
from django.shortcuts import render

class SettingsInvoiceReferenceView(BillingLoginRequiredMixin, View):
    def get(self, request, template_name, *args, **kwargs):
        try:
            return render(request, f"reference/{template_name}.html")
        except TemplateDoesNotExist:
            return HttpResponse(f"Reference file not found for template: {template_name}", status=404)


class SettingsDataManagementView(BillingLoginRequiredMixin, PageTitleMixin, View):
    template_name = "settings_app/data_management.html"
    page_title = "Data Management — Advance Billing"

    def get_organization(self, request):
        from apps.organization.models import Organization  # noqa: PLC0415
        org = getattr(request.user, "organization", None)
        if not org:
            org = Organization.objects.filter(owner=request.user).first()
        return org

    def get(self, request, *args, **kwargs):
        org = self.get_organization(request)
        if not org:
            messages.error(request, "Organization not found for current user.")
            return redirect("organization:index")

        from apps.settings_app.models import OrganizationBackupLog, DataManagementAuditLog  # noqa: PLC0415
        from apps.settings_app.services.backup_service import OrganizationBackupService  # noqa: PLC0415

        setting = OrganizationBackupService.get_or_create_backup_setting(org)
        backup_logs = OrganizationBackupLog.objects.filter(organization=org)[:10]
        audit_logs = DataManagementAuditLog.objects.filter(organization=org)[:10]

        _, counts = OrganizationBackupService.generate_backup_datasets(org)
        total_records = sum(counts.values())

        context = {
            "title": self.page_title,
            "page_title": self.page_title,
            "org": org,
            "backup_setting": setting,
            "backup_logs": backup_logs,
            "audit_logs": audit_logs,
            "counts": counts,
            "total_records": total_records,
            "owner_email": org.owner.email if org.owner else "",
        }
        return render(request, self.template_name, context)

    def post(self, request, *args, **kwargs):
        org = self.get_organization(request)
        if not org:
            messages.error(request, "Organization not found.")
            return redirect("settings_app:data_management")

        from apps.settings_app.services.backup_service import OrganizationBackupService  # noqa: PLC0415
        from apps.settings_app.services.audit_service import DataManagementAuditService  # noqa: PLC0415
        from apps.settings_app.models import DataManagementAction  # noqa: PLC0415

        setting = OrganizationBackupService.get_or_create_backup_setting(org)
        action = request.POST.get("action")

        if action == "toggle_weekly_backup":
            enabled = request.POST.get("weekly_backup_enabled") == "true"
            setting.weekly_backup_enabled = enabled
            if enabled and not setting.next_backup_at:
                from django.utils import timezone  # noqa: PLC0415
                from datetime import timedelta  # noqa: PLC0415
                setting.next_backup_at = timezone.now() + timedelta(days=7)
            setting.save()

            DataManagementAuditService.log_action(
                organization=org,
                user=request.user,
                action=DataManagementAction.WEEKLY_BACKUP_TOGGLE,
                details={"enabled": enabled},
                request=request,
                notify_user=False,
            )

            messages.success(
                request,
                f"Weekly data backup {'enabled' if enabled else 'disabled'}."
            )

        return redirect("settings_app:data_management")


class SettingsDataExportView(BillingLoginRequiredMixin, View):
    """
    Manual Export Download View.
    Generates and streams advance-billing-export-YYYY-MM-DD.zip to the user.
    Unconstrained for legitimate data downloads, protected by dataset boundary and concurrency guard.
    """

    def get(self, request, *args, **kwargs):
        from apps.organization.models import Organization  # noqa: PLC0415
        from apps.settings_app.models import OrganizationBackupLog, BackupTrigger, BackupStatus, DataManagementAction  # noqa: PLC0415
        from apps.settings_app.services.backup_service import OrganizationBackupService, ExportDatasetTooLargeError  # noqa: PLC0415
        from apps.settings_app.services.export_resource_guard import ExportResourceGuard, ExportCapacityExceededError  # noqa: PLC0415
        from apps.settings_app.services.audit_service import DataManagementAuditService  # noqa: PLC0415

        org = getattr(request.user, "organization", None)
        if not org:
            org = Organization.objects.filter(owner=request.user).first()

        if not org or (org.owner != request.user and not request.user.is_superuser):
            messages.error(request, "Only the organization owner can export complete business data.")
            return redirect("settings_app:data_management")

        try:
            with ExportResourceGuard.protect():
                zip_bytes, filename, manifest = OrganizationBackupService.generate_backup_zip(org)

            # Record Log Entry & Audit Log
            OrganizationBackupLog.objects.create(
                organization=org,
                trigger=BackupTrigger.MANUAL,
                status=BackupStatus.SENT,
                record_count=manifest["total_records"],
                file_size_bytes=len(zip_bytes),
                recipient_email=request.user.email,
            )

            DataManagementAuditService.log_action(
                organization=org,
                user=request.user,
                action=DataManagementAction.EXPORT,
                details={"record_count": manifest["total_records"], "filename": filename},
                request=request,
                notify_user=True,
                notification_title="Data Export Downloaded",
                notification_message=f"Manual export ZIP containing {manifest['total_records']} records was generated and downloaded.",
            )

            response = HttpResponse(zip_bytes, content_type="application/zip")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response
        except ExportDatasetTooLargeError as e:
            messages.error(request, str(e))
            return redirect("settings_app:data_management")
        except ExportCapacityExceededError as e:
            return HttpResponse(str(e), status=503, content_type="text/plain")
        except Exception as e:
            messages.error(request, f"Failed to generate data export: {str(e)}")
            return redirect("settings_app:data_management")


@method_decorator(ratelimit(key="user_or_ip", rate="2/h", block=False), name="post")
class SettingsDataBackupMailView(BillingLoginRequiredMixin, View):
    """
    Dedicated Instant Backup Mail View.
    Generates a fresh structured backup ZIP and emails it immediately to the organization owner.
    """

    def post(self, request, *args, **kwargs):
        from django.http import JsonResponse  # noqa: PLC0415
        from apps.organization.models import Organization  # noqa: PLC0415
        from apps.settings_app.models import BackupTrigger, DataManagementAction  # noqa: PLC0415
        from apps.settings_app.services.backup_service import OrganizationBackupService, ExportDatasetTooLargeError  # noqa: PLC0415
        from apps.settings_app.services.export_resource_guard import ExportResourceGuard, ExportCapacityExceededError  # noqa: PLC0415
        from apps.settings_app.services.audit_service import DataManagementAuditService  # noqa: PLC0415
        from apps.common.services.rate_limit import build_ratelimit_429_response  # noqa: PLC0415

        is_json_request = request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in request.headers.get("Accept", "")

        if getattr(request, "limited", False):
            return build_ratelimit_429_response(
                request,
                fn=self.post,
                key="user_or_ip",
                rate="2/h",
                is_json=is_json_request,
                custom_message="Rate limit exceeded. Maximum 2 backup email requests allowed per hour.",
            )

        org = getattr(request.user, "organization", None)
        if not org:
            org = Organization.objects.filter(owner=request.user).first()

        # 1. Organization permission check
        if not org or (org.owner != request.user and not request.user.is_superuser):
            msg = "Only the organization owner can trigger instant backup email delivery."
            if is_json_request:
                return JsonResponse({"success": False, "message": msg}, status=403)
            messages.error(request, msg)
            return redirect("settings_app:data_management")

        if not org:
            if is_json_request:
                return JsonResponse({"success": False, "message": "Organization not found."}, status=400)
            messages.error(request, "Organization not found.")
            return redirect("settings_app:data_management")

        # 2. Owner validation & email check
        owner = getattr(org, "owner", None)
        if not owner or not owner.email:
            msg = "Organization owner email address is not configured."
            if is_json_request:
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect("settings_app:data_management")

        # 3. Generate fresh backup & send email with resource guard
        try:
            with ExportResourceGuard.protect():
                success, result_msg = OrganizationBackupService.send_weekly_backup_email(
                    org, force=True, trigger=BackupTrigger.MANUAL
                )

            if success:
                user_msg = f"Backup emailed successfully to the organization owner ({owner.email})."
                DataManagementAuditService.log_action(
                    organization=org,
                    user=request.user,
                    action=DataManagementAction.BACKUP_SENT,
                    details={"recipient": owner.email, "trigger": "manual"},
                    request=request,
                    notify_user=True,
                    notification_title="Instant Backup Emailed",
                    notification_message=user_msg,
                )
                if is_json_request:
                    return JsonResponse({"success": True, "message": user_msg})
                messages.success(request, user_msg)
            else:
                user_msg = "We couldn't send the backup email. Please try again."
                DataManagementAuditService.log_action(
                    organization=org,
                    user=request.user,
                    action=DataManagementAction.BACKUP_FAILED,
                    details={"error": result_msg, "trigger": "manual"},
                    status="failed",
                    request=request,
                )
                if is_json_request:
                    return JsonResponse({"success": False, "message": user_msg}, status=500)
                messages.error(request, user_msg)

        except ExportDatasetTooLargeError as e:
            user_msg = str(e)
            if is_json_request:
                return JsonResponse({"success": False, "message": user_msg}, status=400)
            messages.error(request, user_msg)
        except ExportCapacityExceededError as e:
            user_msg = str(e)
            if is_json_request:
                return JsonResponse({"success": False, "message": user_msg}, status=503)
            return HttpResponse(user_msg, status=503, content_type="text/plain")
        except Exception as e:
            logger.exception("Instant backup mail failed")
            user_msg = "We couldn't generate the backup. Please try again."
            if is_json_request:
                return JsonResponse({"success": False, "message": user_msg}, status=500)
            messages.error(request, user_msg)

        return redirect("settings_app:data_management")


@method_decorator(ratelimit(key="user_or_ip", rate="5/h", block=False), name="get")
class SettingsExcelExportView(BillingLoginRequiredMixin, View):
    """
    Generates and downloads the official versioned Advance Billing Excel Backup (.xlsx).
    """

    def get(self, request, *args, **kwargs):
        if getattr(request, "limited", False):
            from apps.common.services.rate_limit import build_ratelimit_429_response  # noqa: PLC0415
            return build_ratelimit_429_response(
                request,
                fn=self.get,
                key="user_or_ip",
                rate="5/h",
                is_json=False,
                custom_message="Rate limit exceeded. Maximum 5 Excel export downloads allowed per hour.",
            )

        from apps.organization.models import Organization  # noqa: PLC0415
        from apps.settings_app.services.excel_backup_service import ExcelBackupService  # noqa: PLC0415
        from apps.settings_app.services.backup_service import ExportDatasetTooLargeError  # noqa: PLC0415
        from apps.settings_app.services.export_resource_guard import ExportResourceGuard, ExportCapacityExceededError  # noqa: PLC0415
        from apps.settings_app.services.audit_service import DataManagementAuditService  # noqa: PLC0415
        from apps.settings_app.models import DataManagementAction  # noqa: PLC0415

        org = getattr(request.user, "organization", None)
        if not org:
            org = Organization.objects.filter(owner=request.user).first()

        if not org:
            messages.error(request, "Organization not found.")
            return redirect("settings_app:data_management")

        try:
            with ExportResourceGuard.protect():
                excel_bytes, filename, manifest = ExcelBackupService.generate_backup_workbook(org)
        except ExportDatasetTooLargeError as e:
            messages.error(request, str(e))
            return redirect("settings_app:data_management")
        except ExportCapacityExceededError as e:
            return HttpResponse(str(e), status=503, content_type="text/plain")

        DataManagementAuditService.log_action(
            organization=org,
            user=request.user,
            action=DataManagementAction.EXPORT,
            details=manifest,
            request=request,
            notify_user=False,
        )

        response = HttpResponse(
            excel_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class SettingsExcelImportValidateView(BillingLoginRequiredMixin, View):
    """
    PHASE 1: Read-only validation & dry-run preview for Excel Backups.
    """

    MAX_BACKUP_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

    def post(self, request, *args, **kwargs):
        from apps.organization.models import Organization  # noqa: PLC0415
        from apps.settings_app.services.excel_restore_service import ExcelRestoreService  # noqa: PLC0415

        org = getattr(request.user, "organization", None)
        if not org:
            org = Organization.objects.filter(owner=request.user).first()

        if not org:
            return JsonResponse({"success": False, "message": "Organization not found."}, status=400)

        if "backup_file" not in request.FILES:
            return JsonResponse({"success": False, "message": "Please select an Excel backup (.xlsx) file to validate."}, status=400)

        f = request.FILES["backup_file"]
        if f.size > self.MAX_BACKUP_UPLOAD_SIZE_BYTES:
            return JsonResponse(
                {"success": False, "message": f"Uploaded backup file ({f.size / (1024*1024):.1f} MB) exceeds maximum allowed limit of 25 MB."},
                status=400,
            )

        is_valid, msg, preview = ExcelRestoreService.validate_and_preview(f.read(), f.name, org)

        if is_valid:
            return JsonResponse({"success": True, "message": msg, "preview": preview})
        else:
            return JsonResponse({"success": False, "message": msg}, status=400)


class SettingsExcelImportRestoreView(BillingLoginRequiredMixin, View):
    """
    PHASE 2: Atomic transactional restoration from verified Excel Backup.
    """

    MAX_BACKUP_UPLOAD_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

    def post(self, request, *args, **kwargs):
        from apps.organization.models import Organization  # noqa: PLC0415
        from apps.settings_app.services.excel_restore_service import ExcelRestoreService  # noqa: PLC0415
        from apps.settings_app.services.audit_service import DataManagementAuditService  # noqa: PLC0415
        from apps.settings_app.models import DataManagementAction  # noqa: PLC0415

        org = getattr(request.user, "organization", None)
        if not org:
            org = Organization.objects.filter(owner=request.user).first()

        if not org:
            return JsonResponse({"success": False, "message": "Organization not found."}, status=400)

        if "backup_file" not in request.FILES:
            return JsonResponse({"success": False, "message": "Please select an Excel backup (.xlsx) file to restore."}, status=400)

        f = request.FILES["backup_file"]
        if f.size > self.MAX_BACKUP_UPLOAD_SIZE_BYTES:
            return JsonResponse(
                {"success": False, "message": f"Uploaded backup file ({f.size / (1024*1024):.1f} MB) exceeds maximum allowed limit of 25 MB."},
                status=400,
            )

        success, msg, preview = ExcelRestoreService.execute_restore(f.read(), f.name, org)

        if success:
            messages.success(request, msg)
            DataManagementAuditService.log_action(
                organization=org,
                user=request.user,
                action=DataManagementAction.RESTORE_BACKUP,
                details=preview,
                request=request,
                notify_user=True,
                notification_title="Backup Restored Successfully",
                notification_message=msg,
            )
            return JsonResponse({"success": True, "message": msg, "preview": preview})
        else:
            return JsonResponse({"success": False, "message": msg}, status=400)


class SettingsDangerZoneView(BillingLoginRequiredMixin, View):
    """
    Dedicated Settings View for Danger Zone.
    Renders permanent/destructive account-level operations.
    """
    page_title = "Danger Zone"
    template_name = "settings_app/danger_zone.html"

    def get_organization(self, request):
        from apps.organization.models import Organization  # noqa: PLC0415
        org = getattr(request.user, "organization", None)
        if not org:
            org = Organization.objects.filter(owner=request.user).first()
        return org

    def get(self, request, *args, **kwargs):
        org = self.get_organization(request)
        if not org:
            messages.error(request, "Organization not found for current user.")
            return redirect("organization:index")

        context = {
            "title": self.page_title,
            "page_title": self.page_title,
            "org": org,
            "owner_email": org.owner.email if org.owner else "",
        }
        return render(request, self.template_name, context)


class SettingsDeleteAccountView(BillingLoginRequiredMixin, View):
    """
    Production-Grade Irreversible Organization & Account Deletion view.
    Enforces:
    - POST only (rejects GET requests with redirect/error)
    - CSRF protection
    - Authentication & Organization Owner authorization check
    - Password re-authentication verification
    - Confirmation phrase ("DELETE") exact match
    - Atomic database transaction safe cascading cleanup
    - Invalidation of session and post-deletion redirection
    """

    def get(self, request, *args, **kwargs):
        messages.error(request, "Account deletion cannot be triggered via GET request.")
        return redirect("settings_app:danger_zone")

    def post(self, request, *args, **kwargs):
        from django.contrib.auth import logout
        from django.db import transaction
        from apps.organization.models import Organization  # noqa: PLC0415
        from apps.billing.models import Invoice, InvoiceLine  # noqa: PLC0415
        from apps.customers.models import Customer  # noqa: PLC0415
        from apps.products.models import Product  # noqa: PLC0415
        from apps.common.models import Notification  # noqa: PLC0415
        from apps.settings_app.models import (  # noqa: PLC0415
            OrganizationBackupSetting,
            OrganizationBackupLog,
            DataManagementAuditLog,
            DataManagementAction,
            UserBillPreference,
        )

        org = getattr(request.user, "organization", None)
        if not org:
            org = Organization.objects.filter(owner=request.user).first()

        if not org:
            messages.error(request, "Organization not found for current user.")
            return redirect("settings_app:danger_zone")

        # 1. Authorization: Only the Organization Owner or Superuser can delete
        if org.owner != request.user and not request.user.is_superuser:
            messages.error(
                request,
                "Permission Denied: Only the organization owner can permanently delete the organization."
            )
            return redirect("settings_app:danger_zone")

        # 2. Password Re-Authentication
        password = request.POST.get("password", "")
        if not password or not request.user.check_password(password):
            messages.error(
                request,
                "Deletion Failed: Invalid password. Password re-authentication is required to delete your organization."
            )
            return redirect("settings_app:danger_zone")

        # 3. Explicit Confirmation Phrase Match
        confirmation_phrase = request.POST.get("confirmation_phrase", "")
        if confirmation_phrase != "DELETE":
            messages.error(
                request,
                "Deletion Failed: You must type 'DELETE' in exact uppercase letters to confirm deletion."
            )
            return redirect("settings_app:danger_zone")

        # 4. Atomic Transactional Deletion
        business_name = org.business_name
        user = request.user

        try:
            with transaction.atomic():
                # Record Audit Log before deletion
                DataManagementAuditLog.objects.create(
                    organization=org,
                    user=user,
                    action=DataManagementAction.PERMANENT_DELETE,
                    status="success",
                    details={
                        "organization_name": business_name,
                        "owner_email": user.email,
                        "ip_address": request.META.get("REMOTE_ADDR"),
                    },
                )

                # Delete dependent records in dependency order
                InvoiceLine.objects.filter(invoice__organization=org).delete()
                Invoice.objects.filter(organization=org).delete()
                Customer.objects.filter(organization=org).delete()
                Product.objects.filter(organization=org).delete()
                Notification.objects.filter(organization=org).delete()
                OrganizationBackupSetting.objects.filter(organization=org).delete()
                OrganizationBackupLog.objects.filter(organization=org).delete()
                UserBillPreference.objects.filter(user=user).delete()

                # Delete Organization
                org.delete()

                # Logout user session cleanly
                logout(request)

            messages.success(
                request,
                f"Your organization '{business_name}' and all associated data have been permanently deleted."
            )
            return redirect("auth:login")

        except Exception as exc:
            messages.error(
                request,
                "We couldn't complete the deletion due to a system error. Your data has not been deleted. Please try again."
            )
            return redirect("settings_app:data_management")


