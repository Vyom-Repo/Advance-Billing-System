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
from .forms import UserProfileForm, SettingsPasswordChangeForm, InvoicePreferenceForm
from .models import UserPreference, InvoicePreference


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

