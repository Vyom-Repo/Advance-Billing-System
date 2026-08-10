import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from apps.invoices.services.invoice_preview_service import InvoicePreviewService

User = get_user_model()
user = User.objects.first()

context = InvoicePreviewService.get_preview_context(user, preview_mode="demo")
print("Company Name:", context['company']['name'])
print("Bank Name:", context['company'].get('bank_name'))
print("Logo URL:", context['company'].get('logo_url'))
print("Signature URL:", context['company'].get('signature_url'))
