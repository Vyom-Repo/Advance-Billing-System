import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from django.template.loader import render_to_string

User = get_user_model()
user = User.objects.first()

templates_dir = "templates/pdf"
templates = [f for f in os.listdir(templates_dir) if f.endswith(".html")]

preferences_list = [
    "show_company_logo", "show_company_header", "show_company_footer", 
    "show_qr_code", "show_bank_details", "show_gst_summary", "show_hsn_sac", 
    "show_signature", "show_terms", "show_payment_info", "show_page_numbers", 
    "show_print_date", "print_on_letterhead"
]

def run_test(test_name, prefs_config):
    print(f"\n--- Running {test_name} ---")
    for tmpl in sorted(templates):
        prefs = prefs_config.copy()
        prefs['template_name'] = tmpl.replace(".html", "")
        context = InvoicePreviewService.get_preview_context(user, custom_prefs=prefs, preview_mode="demo")
        try:
            html = render_to_string(f"pdf/{tmpl}", context)
            
            if not prefs.get('show_bank_details') and ("IFSC:" in html or "Account No:" in html or "Bank Details:" in html):
                print(f"[{tmpl}] FAIL: Bank details ghost found")
            if not prefs.get('show_company_logo') and ("<img class=\"logo\"" in html or "class=\"logo-mark\"" in html):
                print(f"[{tmpl}] FAIL: Logo ghost found")
            if not prefs.get('show_qr_code') and ("class=\"qr-image\"" in html or ("class=\"qr\"" in html and "<img" in html.split("class=\"qr\"")[1][:150])):
                print(f"[{tmpl}] FAIL: QR code ghost found")
            if not prefs.get('show_signature') and ("Authorized Signatory" in html or "Authorised Signatory" in html or "class=\"signature-image\"" in html):
                print(f"[{tmpl}] FAIL: Signature ghost found")
            if not prefs.get('show_hsn_sac') and (">HSN/SAC<" in html or ">HSN<" in html):
                print(f"[{tmpl}] FAIL: HSN ghost found")
            if not prefs.get('show_gst_summary') and ("Central Tax" in html or "State/UT Tax" in html):
                print(f"[{tmpl}] FAIL: GST Summary ghost found")
            if not prefs.get('show_terms') and "Terms and Conditions:" in html:
                print(f"[{tmpl}] FAIL: Terms ghost found")
            if not prefs.get('show_payment_info') and "Amount Paid" in html:
                print(f"[{tmpl}] FAIL: Payment info ghost found")
            if not prefs.get('show_page_numbers') and ("Page 1" in html or "Page 1/1" in html):
                print(f"[{tmpl}] FAIL: Page numbers ghost found")
            if not prefs.get('show_company_footer') and "digitally signed document" in html:
                print(f"[{tmpl}] FAIL: Company footer ghost found")
        except Exception as e:
            print(f"[{tmpl}] FAIL: Rendering exception - {e}")

all_on = {p: True for p in preferences_list}
run_test("TEST 1: Everything ON", all_on)

tests = {
    "TEST 2: Logo OFF": "show_company_logo",
    "TEST 3: Bank OFF": "show_bank_details",
    "TEST 4: QR OFF": "show_qr_code",
    "TEST 5: Signature OFF": "show_signature",
    "TEST 6: HSN/SAC OFF": "show_hsn_sac",
    "TEST 7: GST Summary OFF": "show_gst_summary",
    "TEST 8: Terms OFF": "show_terms",
    "TEST 9: Payment Info OFF": "show_payment_info",
    "TEST 10: Company Footer OFF": "show_company_footer",
    "TEST 11: Page Numbers OFF": "show_page_numbers",
    "TEST 12: Print Date OFF": "show_print_date"
}

for test_name, pref_to_disable in tests.items():
    cfg = all_on.copy()
    cfg[pref_to_disable] = False
    run_test(test_name, cfg)

all_off = {p: False for p in preferences_list}
run_test("TEST 13: Multiple preferences OFF simultaneously", all_off)

print("\nMatrix tests complete.")
