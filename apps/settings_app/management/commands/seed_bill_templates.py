"""
apps/settings_app/management/commands/seed_bill_templates.py

Idempotent command that populates the BillTemplate table with all
known template slugs, their display names, file paths, and default configs.

Usage:
    python manage.py seed_bill_templates
    python manage.py seed_bill_templates --force   # overwrite default_config even if already seeded
"""

from django.core.management.base import BaseCommand

# Canonical template registry.
# Extend this list when a new PDF template file is added.
TEMPLATES = [
    {
        "slug":               "letterhead_invoice",
        "name":               "Company Letterhead Invoice",
        "description":        "Dedicated production-ready invoice template designed specifically for Company Letterhead rendering.",
        "template_file_path": "pdf/letterhead_invoice.html",
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": True,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": True,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": False, "has_description_column": True,
            "has_receiver_signature": False, "has_dispatch_from": False,
            "simplified_items": False,
        },
    },
    {
        "slug":               "simple_invoice",
        "name":               "Simple Professional",
        "description":        "Clean, robust, professional invoice template. Guaranteed 100% compatible with WeasyPrint & letterhead rendering.",
        "template_file_path": "pdf/simple_invoice.html",
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": True,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": False, "has_description_column": True,
            "has_receiver_signature": False, "has_dispatch_from": False,
            "simplified_items": False,
        },
    },
    {
        "slug":               "compact_template",
        "name":               "Compact",
        "description":        "Dense two-column GST invoice with integrated tax summary table. Good for retail.",
        "template_file_path": "pdf/compact_template.html",
        "default_config": {
            # Layout
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Compact",
            # Visibility
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            # Capabilities
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
        "slug":               "genz",
        "name":               "GenZ",
        "description":        "Modern blue brand-bar design with meta-cells and gradient totals box.",
        "template_file_path": "pdf/genz.html",
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": False, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": False,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": False,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": True, "has_description_column": False,
            "has_receiver_signature": False, "has_dispatch_from": False,
            "simplified_items": False,
        },
    },
    {
        "slug":               "landscape_template",
        "name":               "Landscape",
        "description":        "A4 landscape orientation with full CGST/SGST breakdown table. Ideal for multiple line items.",
        "template_file_path": "pdf/landscape_template.html",
        "default_config": {
            "paper_size": "A4", "orientation": "Landscape", "margins": "Normal",
            "font_size": "Small", "table_density": "Compact",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": True,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": False, "has_description_column": False,
            "has_receiver_signature": True, "has_dispatch_from": False,
            "simplified_items": False,
        },
    },
    {
        "slug":               "modern_template",
        "name":               "Modern",
        "description":        "Clean 3-column header with info-box grid and circular signature stamp.",
        "template_file_path": "pdf/modern_template.html",
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": False,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": True, "has_description_column": False,
            "has_receiver_signature": False, "has_dispatch_from": False,
            "simplified_items": False,
        },
    },
    {
        "slug":               "mrp_discount_template",
        "name":               "MRP + Discount",
        "description":        "Retail template showing MRP, selling price, and discount columns.",
        "template_file_path": "pdf/mrp_discount_template.html",
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": False,
            "has_mrp_column": True, "has_selling_price_column": True,
            "has_product_images": False, "has_description_column": False,
            "has_receiver_signature": False, "has_dispatch_from": False,
            "simplified_items": False,
        },
    },
    {
        "slug":               "professional_template",
        "name":               "Professional",
        "description":        "Classic professional invoice with Bill To / Ship To grid, receiver signature line.",
        "template_file_path": "pdf/professional_template.html",
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": False,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": False, "has_description_column": True,
            "has_receiver_signature": True, "has_dispatch_from": False,
            "simplified_items": False,
        },
    },
    {
        "slug":               "service_template",
        "name":               "Service",
        "description":        "Simplified service invoice — description + amount, no qty/rate. Pink header bar.",
        "template_file_path": "pdf/service_template.html",
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
            "custom_footer_message": "Thank you for your business.",
            "has_qr": True, "has_signature": True, "has_logo": True,
            "has_bank_details": True, "has_gst_summary": True, "has_hsn_sac": True,
            "has_tax_summary_table": False,
            "has_mrp_column": False, "has_selling_price_column": False,
            "has_product_images": False, "has_description_column": False,
            "has_receiver_signature": False, "has_dispatch_from": False,
            "simplified_items": True,
        },
    },
    {
        "slug":               "vintage",
        "name":               "Vintage",
        "description":        "Absolute-positioned invoice-in-a-frame design with GST breakdown table. Premium look.",
        "template_file_path": "pdf/vintage.html",
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Compact",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
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
    {
        "slug":               "ledger_classic",
        "name":               "Ledger Classic",
        "description":        "Traditional accountant-ledger style with ruled grid tables, double underlines, and tabular numerals.",
        "template_file_path": "pdf/ledger_classic.html",
        "is_active":          True,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Compact",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
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
    {
        "slug":               "minimal_mono",
        "name":               "Minimal Mono",
        "description":        "Modern minimalist layout with generous whitespace, borderless alignment, and clean typography.",
        "template_file_path": "pdf/minimal_mono.html",
        "is_active":          True,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
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
    {
        "slug":               "bold_header",
        "name":               "Bold Header",
        "description":        "High-contrast colored header band with modern badge metadata and carded sectioning.",
        "template_file_path": "pdf/bold_header.html",
        "is_active":          True,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
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
    {
        "slug":               "elegant_serif",
        "name":               "Elegant Serif",
        "description":        "Formal serif typography with centered letterhead branding, delicate hairlines, and advisory styling.",
        "template_file_path": "pdf/elegant_serif.html",
        "is_active":          True,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
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
    {
        "slug":               "tech_grid",
        "name":               "Tech Grid",
        "description":        "Modern tech and agency invoice rendering line items as individual bordered cards with badge pills.",
        "template_file_path": "pdf/tech_grid.html",
        "is_active":          True,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Small", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
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
    # Slugs that exist in DocumentPreference choices but have no PDF yet
    {
        "slug":               "gst_classic",
        "name":               "GST Classic",
        "description":        "Classic GST invoice (template file coming soon).",
        "template_file_path": "pdf/gst_classic.html",
        "is_active":          False,
        "default_config": {
            "paper_size": "A4", "orientation": "Portrait", "margins": "Normal",
            "font_size": "Medium", "table_density": "Comfortable",
            "show_company_header": True, "show_company_logo": True, "show_company_footer": True,
            "print_on_letterhead": False,
            "show_qr_code": True, "show_bank_details": True, "show_gst_summary": True,
            "show_hsn_sac": True, "show_signature": True, "show_terms": True,
            "show_payment_info": True, "show_page_numbers": True, "show_print_date": True,
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
            slug   = tpl["slug"]
            is_active = tpl.pop("is_active", True)
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
            elif force:
                obj.default_config     = config
                obj.name               = tpl["name"]
                obj.description        = tpl.get("description", "")
                obj.template_file_path = tpl["template_file_path"]
                obj.is_active          = is_active
                obj.save()
                updated_count += 1
                if options.get("verbosity", 1) > 0:
                    self.stdout.write(self.style.WARNING(f"  [UPDATED] {slug}"))
            else:
                skipped_count += 1
                if options.get("verbosity", 1) > 0:
                    self.stdout.write(f"  [SKIP]    {slug} (already exists; use --force to overwrite)")

        if options.get("verbosity", 1) > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nDone: {created_count} created, {updated_count} updated, {skipped_count} skipped."
                )
            )
