"""
apps/settings_app/management/commands/seed_bill_templates.py

Idempotent command that populates the BillTemplate table with all
known template slugs, their display names, file paths, and default configs.

Three official customer templates are active:
1. Professional (professional_template) - Recommended
2. Compact (compact_template) - High Density
3. Vintage (vintage) - Classic Frame

Usage:
    python manage.py seed_bill_templates
    python manage.py seed_bill_templates --force   # overwrite default_config even if already seeded
"""

from django.core.management.base import BaseCommand

# Canonical template registry.
# The 3 active templates are listed first in order of preference.
TEMPLATES = [
    {
        "slug":               "professional_template",
        "name":               "Professional",
        "description":        "Clean, modern, corporate business invoice template. Recommended default.",
        "template_file_path": "pdf/professional_template.html",
        "is_active":          True,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": False,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": False, "has_description_column": True,
            "has_receiver_signature": False, "has_dispatch_from": False,
            "simplified_items": False,
        },
    },
    {
        "slug":               "compact_template",
        "name":               "Compact",
        "description":        "Efficient, high-density GST business invoice with compact table layout.",
        "template_file_path": "pdf/compact_template.html",
        "is_active":          True,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Compact",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": True,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": False, "has_description_column": False,
            "has_receiver_signature": False, "has_dispatch_from": True,
            "simplified_items": False,
        },
    },
    {
        "slug":               "vintage",
        "name":               "Vintage",
        "description":        "Premium, classic invoice with traditional stationery framing.",
        "template_file_path": "pdf/vintage.html",
        "is_active":          True,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Compact",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": True,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": False, "has_description_column": False,
            "has_receiver_signature": False, "has_dispatch_from": False,
            "simplified_items": False,
        },
    },
    # Archived legacy templates (is_active=False: renderable for historical bills, hidden from gallery)
    {
        "slug":               "letterhead_invoice",
        "name":               "Company Letterhead Invoice",
        "description":        "Dedicated production-ready invoice template designed specifically for Company Letterhead rendering.",
        "template_file_path": "pdf/letterhead_invoice.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": True,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "simple_invoice",
        "name":               "Simple Professional",
        "description":        "Clean, robust, professional invoice template.",
        "template_file_path": "pdf/simple_invoice.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "genz",
        "name":               "GenZ",
        "description":        "Legacy GenZ blue brand-bar design.",
        "template_file_path": "pdf/genz.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": False, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": False,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "landscape_template",
        "name":               "Landscape",
        "description":        "Legacy A4 landscape orientation.",
        "template_file_path": "pdf/landscape_template.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Landscape", "margins": "Normal",
            "font_size": "Small", "table_density": "Compact",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "modern_template",
        "name":               "Modern",
        "description":        "Legacy Modern 3-column header template.",
        "template_file_path": "pdf/modern_template.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "mrp_discount_template",
        "name":               "MRP + Discount",
        "description":        "Legacy Retail template showing MRP and discount columns.",
        "template_file_path": "pdf/mrp_discount_template.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "service_template",
        "name":               "Service",
        "description":        "Legacy simplified service invoice.",
        "template_file_path": "pdf/service_template.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "ledger_classic",
        "name":               "Ledger Classic",
        "description":        "Legacy accountant-ledger style.",
        "template_file_path": "pdf/ledger_classic.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Compact",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "minimal_mono",
        "name":               "Minimal Mono",
        "description":        "Legacy minimalist layout.",
        "template_file_path": "pdf/minimal_mono.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "bold_header",
        "name":               "Bold Header",
        "description":        "Legacy colored header band template.",
        "template_file_path": "pdf/bold_header.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "elegant_serif",
        "name":               "Elegant Serif",
        "description":        "Legacy formal serif typography template.",
        "template_file_path": "pdf/elegant_serif.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
    {
        "slug":               "tech_grid",
        "name":               "Tech Grid",
        "description":        "Legacy tech grid template.",
        "template_file_path": "pdf/tech_grid.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
        },
    },
]


class Command(BaseCommand):
    help = "Seed the BillTemplate table with all known invoice template configurations."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite default_config for existing rows.",
        )

    def handle(self, *args, **options):
        from apps.settings_app.models import BillTemplate

        force = options["force"]
        created_count = updated_count = skipped_count = 0

        for tpl in TEMPLATES:
            slug = tpl["slug"]
            is_active = tpl.get("is_active", True)
            config = tpl["default_config"]

            obj, created = BillTemplate.objects.get_or_create(
                slug=slug,
                defaults={
                    "name":               tpl["name"],
                    "description":        tpl.get("description", ""),
                    "template_file_path": tpl["template_file_path"],
                    "is_active":          is_active,
                    "default_config":     config,
                },
            )

            if created:
                created_count += 1
                if options.get("verbosity", 1) > 0:
                    self.stdout.write(self.style.SUCCESS(f"  [CREATED] {slug}"))
            else:
                # Idempotent update: modify fields in place without deleting/recreating records
                obj.name               = tpl["name"]
                obj.description        = tpl.get("description", "")
                obj.template_file_path = tpl["template_file_path"]
                obj.is_active          = is_active
                if force:
                    obj.default_config = config
                obj.save()
                updated_count += 1
                if options.get("verbosity", 1) > 0:
                    self.stdout.write(self.style.WARNING(f"  [UPDATED] {slug}"))

        if options.get("verbosity", 1) > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nDone: {created_count} created, {updated_count} updated, {skipped_count} skipped."
                )
            )
