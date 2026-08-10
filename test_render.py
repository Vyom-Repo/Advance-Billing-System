import os
import django
from django.template.loader import render_to_string

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from apps.settings_app.models import DocumentPreference

User = get_user_model()
user = User.objects.first()

prefs_obj, _ = DocumentPreference.objects.get_or_create(user=user)
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

context = InvoicePreviewService.get_preview_context(user, custom_prefs=prefs)
html_string = render_to_string('pdf/evergreen.html', context)
print(html_string[:1000])
