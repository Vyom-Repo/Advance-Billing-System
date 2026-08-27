"""apps/organization/admin.py"""
from django.contrib import admin
from .models import Organization, BankAccount, UpgradeRequest


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    """
    Admin registration for Organization.

    The `plan` field is intentionally editable here so that the administrator
    can mark accounts as PAID without needing a separate Phase 2 dashboard.
    """
    list_display = ("business_name", "owner", "plan", "is_gst_registered", "created_at")
    list_filter = ("plan", "is_gst_registered")
    search_fields = ("business_name", "owner__email", "gstin")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Plan / Billing Status", {
            "fields": ("plan",),
            "description": (
                "Set to 'Paid' to remove the Advance Billing watermark from this organization's invoices. "
                "Set to 'Free' to restore the watermark."
            ),
        }),
        ("Business Information", {
            "fields": (
                "owner", "business_name", "legal_business_name",
                "is_gst_registered", "gstin", "pan", "state_code",
            ),
        }),
        ("Contact & Address", {
            "fields": (
                "business_email", "phone_number",
                "address_line_1", "address_line_2", "city", "state", "pincode", "country",
            ),
        }),
        ("Branding", {
            "fields": ("logo", "letterhead", "letterhead_header_offset", "letterhead_footer_offset", "signature", "qr_code"),
        }),
        ("Signature & Disclaimer", {
            "fields": ("signature_mode", "authorized_signatory_name", "show_computer_generated_disclaimer"),
        }),
        ("Terms & Conditions", {
            "fields": ("terms_and_conditions",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ("organization", "bank_name", "account_name", "account_number", "ifsc_code", "is_default")
    list_filter = ("is_default",)
    search_fields = ("organization__business_name", "bank_name", "account_number", "ifsc_code")


@admin.register(UpgradeRequest)
class UpgradeRequestAdmin(admin.ModelAdmin):
    list_display = ("organization", "requester_name", "requester_email", "status", "created_at", "approved_at")
    list_filter = ("status", "created_at")
    search_fields = ("organization__business_name", "requester_name", "requester_email")
    readonly_fields = ("created_at", "updated_at")
