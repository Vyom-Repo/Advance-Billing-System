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
    path("invoice-design/", views.SettingsInvoiceDesignView.as_view(), name="invoice_design"),
    path("invoice-design/preview/", views.SettingsInvoiceDesignPreviewAPIView.as_view(), name="invoice_design_preview"),
    path("invoice-design/download/", views.SettingsInvoiceDesignDownloadView.as_view(), name="invoice_design_download"),
    path("invoice-design/reference/<str:template_name>/", views.SettingsInvoiceReferenceView.as_view(), name="invoice_design_reference"),
    path("notifications/", views.SettingsNotificationsView.as_view(), name="notifications"),
    path("data-management/", views.SettingsDataManagementView.as_view(), name="data_management"),
    path("data-management/export/", views.SettingsDataExportView.as_view(), name="data_export"),
    path("data-management/backup/mail/", views.SettingsDataBackupMailView.as_view(), name="data_backup_mail"),
    path("data-management/excel-export/", views.SettingsExcelExportView.as_view(), name="excel_export"),
    path("data-management/excel-import-validate/", views.SettingsExcelImportValidateView.as_view(), name="excel_import_validate"),
    path("data-management/excel-import-restore/", views.SettingsExcelImportRestoreView.as_view(), name="excel_import_restore"),
    path("danger-zone/", views.SettingsDangerZoneView.as_view(), name="danger_zone"),
    path("danger-zone/delete-account/", views.SettingsDeleteAccountView.as_view(), name="delete_account"),
    # Phase 1: Free tier upgrade request
    path("upgrade/", views.SettingsUpgradeView.as_view(), name="upgrade"),
]
