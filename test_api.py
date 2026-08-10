import os
import django
import json
from django.test import Client

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()
user = User.objects.first()

client = Client()
client.force_login(user)

payload = {
    'template_name': 'professional_template',
    'show_company_logo': True,
    'show_bank_details': True,
    'show_qr_code': True,
    'show_signature': True,
}

url = reverse('settings_app:invoice_design_preview')
response = client.post(url, data=json.dumps(payload), content_type='application/json')
print("Status Code:", response.status_code)
content = response.content.decode('utf-8')
print("Contains Acme Global Solutions (Demo):", "Acme Global Solutions (Demo)" in content)
print("Contains Demo Bank of India:", "Demo Bank of India" in content)
