import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from apps.common.services.layout_engine import PrintableFrameBuilder

User = get_user_model()
user = User.objects.get(email='vyomprajapati149@gmail.com')
context = InvoicePreviewService.get_preview_context(user)
context['prefs'] = {}
context['prefs']['print_on_letterhead'] = True
context['org'].letterhead_header_offset = 80
context['layout_frame'] = PrintableFrameBuilder.build_frame(context['org'], context['prefs'])
print(context['layout_frame'])
html = render_to_string("pdf/professional.html", context)
with open("media/test.html", "w") as f:
    f.write(html)
print("Done")
