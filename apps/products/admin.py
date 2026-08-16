"""
apps/products/admin.py — Product Admin Registration
"""
from django.contrib import admin
from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name", "product_type", "taxability_type",
        "gst_rate", "unit_price", "price_basis", "uqc",
        "organization", "created_at",
    )
    list_filter = ("product_type", "taxability_type", "cess_applicable", "reverse_charge_applicable")
    search_fields = ("name", "hsn_code", "sac_code", "organization__business_name")
    readonly_fields = ("uuid", "created_at", "updated_at")
    ordering = ("-created_at",)
