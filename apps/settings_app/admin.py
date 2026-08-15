"""
apps/settings_app/admin.py

Django admin configuration for settings_app models.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import DocumentPreference, InvoicePreference, BillTemplate, UserBillPreference


@admin.register(BillTemplate)
class BillTemplateAdmin(admin.ModelAdmin):
    list_display  = ("slug", "name", "is_active", "created_at", "preview_thumbnail")
    list_filter   = ("is_active",)
    search_fields = ("slug", "name", "description")
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {
            "fields": ("slug", "name", "description", "template_file_path", "is_active"),
        }),
        ("Configuration", {
            "fields": ("default_config",),
            "description": (
                "JSON object: every key is a preference toggle or capability flag for this "
                "template. Only keys listed here are treated as valid by resolve_render_config()."
            ),
        }),
        ("Gallery", {
            "fields": ("preview_image",),
        }),
        ("Metadata", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    def preview_thumbnail(self, obj):
        if obj.preview_image:
            return format_html('<img src="{}" style="height:40px;border-radius:4px;">', obj.preview_image.url)
        return "—"
    preview_thumbnail.short_description = "Preview"


@admin.register(UserBillPreference)
class UserBillPreferenceAdmin(admin.ModelAdmin):
    list_display   = ("user", "template", "updated_at")
    list_filter    = ("template",)
    search_fields  = ("user__email", "template__slug")
    readonly_fields = ("updated_at",)
    raw_id_fields  = ("user",)


@admin.register(DocumentPreference)
class DocumentPreferenceAdmin(admin.ModelAdmin):
    list_display  = ("user", "template_name", "paper_size", "orientation")
    list_filter   = ("template_name", "paper_size", "orientation")
    search_fields = ("user__email",)
    raw_id_fields = ("user",)


@admin.register(InvoicePreference)
class InvoicePreferenceAdmin(admin.ModelAdmin):
    list_display  = ("user", "invoice_prefix", "default_currency")
    search_fields = ("user__email", "invoice_prefix")
    raw_id_fields = ("user",)
