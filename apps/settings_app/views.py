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
            org = Organization.objects.filter(user=self.request.user).first()
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
        
        from apps.common.models import Notification
        from django.utils import timezone
        from django.utils.timesince import timesince
        
        now = timezone.now()
        today_date = now.date()
        yesterday_date = today_date - timezone.timedelta(days=1)
        
        db_notifications = Notification.objects.filter(user=self.request.user).order_by('-created_at')
        
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
                
            # Assign icons based on category
            if n.category == "billing":
                icon = "file-text"
                icon_color = "var(--color-success)"
                icon_bg = "var(--color-success-bg)"
            elif n.category == "customers":
                icon = "users"
                icon_color = "var(--color-info)"
                icon_bg = "var(--color-info-bg)"
            elif n.category == "organization":
                icon = "building"
                icon_color = "var(--color-text-secondary)"
                icon_bg = "var(--color-bg-raised)"
            elif n.category == "security":
                icon = "shield"
                icon_color = "var(--color-warning)"
                icon_bg = "var(--color-warning-bg)"
            elif n.category == "settings":
                icon = "settings"
                icon_color = "var(--color-text-secondary)"
                icon_bg = "var(--color-bg-raised)"
            else:
                icon = "bell"
                icon_color = "var(--color-accent)"
                icon_bg = "var(--color-accent-subtle)"
                
            notifications.append({
                "id": str(n.id),
                "title": n.title,
                "desc": n.message,
                "category": n.category,
                "icon": icon,
                "icon_color": icon_color,
                "icon_bg": icon_bg,
                "is_read": n.is_read,
                "group": group,
                "time": time_str,
                "action_url": "#"
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

class SettingsInvoiceDesignPreviewAPIView(BillingLoginRequiredMixin, View):
    """
    Renders a PDF preview using the unified render_bill_pdf pipeline.

    Accepts a JSON body with any DocumentPreference fields plus an optional
    ``template_name`` key.  The posted values are treated as one-off
    request_overrides — they are NOT saved to the database.
    """
    def post(self, request, *args, **kwargs):
        try:
            from apps.invoices.services.invoice_preview_service import InvoicePreviewService
            from apps.invoices.services.bill_serializer import serialize_bill_for_render
            from apps.common.services.sample_data_service import SampleDataService
            from apps.common.services.organization_service import OrganizationService
            from apps.common.services.layout_engine import PrintableFrameBuilder

            data = json.loads(request.body)
            template_slug = data.get("template_name", "gst_classic")
            template_path = f"pdf/{template_slug}.html"

            # Resolve config (template defaults + user prefs + request body as overrides)
            config = InvoicePreviewService.resolve_render_config(
                template_slug=template_slug,
                user=request.user,
                request_overrides=data,
            )

            # Build org / company data
            org_data = OrganizationService.get_company_assets(request.user)
            if org_data:
                org_obj = org_data["organization"]
                company = {
                    "name": org_data["business_name"],
                    "address": f"{org_data['address_line_1']} {org_data['address_line_2']}".strip(),
                    "city": org_data["city"],
                    "state": org_data["state"],
                    "gstin": org_data["gstin"],
                    "email": org_data["email"],
                    "phone": org_data["phone"],
                }
                if org_data["default_bank"]:
                    company["bank_name"] = org_data["default_bank"].bank_name
                    company["acc_no"]    = org_data["default_bank"].account_number
                    company["ifsc"]      = org_data["default_bank"].ifsc_code
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

        except Exception as e:
            import traceback
            return HttpResponse(
                f"<div style='color:red;padding:20px;'>Error rendering preview: {e}<br><pre>{traceback.format_exc()}</pre></div>",
                status=400,
            )

class SettingsInvoiceDesignDownloadView(BillingLoginRequiredMixin, View):
    """
    Generates a PDF download using the user's saved DocumentPreference settings.
    Supports query parameters e.g. ?letterhead=true or ?print_on_letterhead=1.
    Uses the unified render_bill_pdf pipeline with automatic fallback.
    """
    def get(self, request, *args, **kwargs):
        if not HTML:
            return HttpResponse("WeasyPrint is not installed or configured correctly.", status=500)

        from apps.invoices.services.invoice_preview_service import InvoicePreviewService
        from apps.invoices.services.bill_serializer import serialize_bill_for_render
        from apps.common.services.sample_data_service import SampleDataService
        from apps.common.services.organization_service import OrganizationService
        from apps.common.services.layout_engine import PrintableFrameBuilder
        from apps.settings_app.models import DocumentPreference

        template_slug = "letterhead_invoice"
        template_path = "pdf/letterhead_invoice.html"

        # Check for letterhead GET parameter overrides
        request_overrides = {}
        lh_param = request.GET.get("letterhead") or request.GET.get("print_on_letterhead")
        if lh_param is not None:
            request_overrides["print_on_letterhead"] = lh_param.lower() in ("true", "1", "yes", "on")

        config = InvoicePreviewService.resolve_render_config(
            template_slug=template_slug,
            user=request.user,
            request_overrides=request_overrides if request_overrides else None,
        )

        org_data = OrganizationService.get_company_assets(request.user)
        if org_data:
            org_obj = org_data["organization"]
            company = {
                "name":    org_data["business_name"],
                "address": f"{org_data['address_line_1']} {org_data['address_line_2']}".strip(),
                "city":    org_data["city"],
                "state":   org_data["state"],
                "gstin":   org_data["gstin"],
                "email":   org_data["email"],
                "phone":   org_data["phone"],
            }
            if org_data["default_bank"]:
                company["bank_name"] = org_data["default_bank"].bank_name
                company["acc_no"]    = org_data["default_bank"].account_number
                company["ifsc"]      = org_data["default_bank"].ifsc_code
        else:
            org_obj = None
            company = SampleDataService.sample_company()

        invoice  = SampleDataService.sample_invoice(request.user)
        customer = SampleDataService.sample_customer()
        items    = SampleDataService.sample_items()

        bill_data    = serialize_bill_for_render(invoice, customer, items, company, org_obj)
        layout_frame = PrintableFrameBuilder.build_frame(org_obj, config)

        pdf_bytes = InvoicePreviewService.render_bill_pdf(
            bill_data=bill_data,
            config=config,
            template_file_path=template_path,
            layout_frame=layout_frame,
            org=org_obj,
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

