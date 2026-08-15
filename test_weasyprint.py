import os
import django
from django.template.loader import render_to_string
from weasyprint import HTML

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from apps.settings_app.models import DocumentPreference

User = get_user_model()
user = User.objects.first()

if not user:
    print("No user found, cannot run test.")
    exit(1)

prefs_obj, _ = DocumentPreference.objects.get_or_create(user=user)
# Enable all preferences to test full rendering
prefs = {
    'show_company_logo': True,
    'show_company_header': True,
    'show_company_footer': True,
    'show_qr_code': True,
    'show_bank_details': True,
    'show_gst_summary': True,
    'show_hsn_sac': True,
    'show_signature': True,
    'show_terms': True,
    'show_payment_info': True,
    'show_page_numbers': True,
    'show_print_date': True,
    'print_on_letterhead': False,
    'paper_size': 'A4',
    'orientation': 'Portrait',
    'margins': 'Normal',
}

context = InvoicePreviewService.get_preview_context(user, custom_prefs=prefs, preview_mode="demo")

template_files = [
    'compact_template.html',
    'genz.html',
    'landscape_template.html',
    'modern_template.html',
    'mrp_discount_template.html',
    'professional_template.html',
    'service_template.html',
    'vintage.html'
]

print("=== PDF RENDERING TEST ===")
all_valid = True
for filename in template_files:
    template_path = f"pdf/{filename}"
    pdf_output = f"{filename}.pdf"
    try:
        html_string = render_to_string(template_path, context)
        html = HTML(string=html_string, base_url="file:///")
        html.write_pdf(pdf_output)
        print(f"[OK] {filename}")
        os.remove(pdf_output)
    except Exception as e:
        import traceback
        print(f"[ERROR] {filename}:")
        traceback.print_exc()
        all_valid = False

if all_valid:
    print("\nAll templates rendered to PDF successfully.")
else:
    print("\nSome templates failed to render.")
