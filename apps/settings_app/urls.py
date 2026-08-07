"""apps/settings_app/urls.py"""
from django.urls import path
from django.views.generic import RedirectView, TemplateView
from . import views

app_name = "settings_app"

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="settings_app:profile", permanent=False), name="index"),
    path("profile/", views.SettingsProfileView.as_view(), name="profile"),
    path("profile/change-email/", views.SettingsChangeEmailView.as_view(), name="change_email"),
    path("profile/verify/", views.SettingsProfileVerifyView.as_view(), name="profile_verify"),
    path("security/", views.SettingsSecurityView.as_view(), name="security"),
    path("security/verify/", views.SettingsSecurityVerifyView.as_view(), name="security_verify"),
    path("appearance/", views.SettingsAppearanceView.as_view(), name="appearance"),
    path("system/", views.SettingsSystemView.as_view(), name="system"),
    
    # Future Settings
    path("invoice-preferences/", views.SettingsInvoicePreferencesView.as_view(), name="invoice_preferences"),
    path("pdf-printing/", TemplateView.as_view(template_name="settings_app/coming_soon.html", extra_context={"feature_name": "PDF & Printing", "feature_desc": "Design your invoice PDFs with custom templates and signatures.", "feature_icon": "printer"}), name="pdf_printing"),
    path("notifications/", views.SettingsNotificationsView.as_view(), name="notifications"),
    path("data-management/", TemplateView.as_view(template_name="settings_app/coming_soon.html", extra_context={"feature_name": "Data Management", "feature_desc": "Export your data, manage backups, and view audit logs.", "feature_icon": "database"}), name="data_management"),
    path("delete-account/", TemplateView.as_view(template_name="settings_app/coming_soon.html", extra_context={"feature_name": "Delete Account", "feature_desc": "Permanently remove your account and all associated data.", "feature_icon": "trash-2"}), name="delete_account"),
]
