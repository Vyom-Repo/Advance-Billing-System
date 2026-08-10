import os
import re

templates_dir = "templates/pdf"
templates = [f for f in os.listdir(templates_dir) if f.endswith(".html")]

prefs = [
    "show_company_logo",
    "show_company_header",
    "show_company_footer",
    "show_qr_code",
    "show_bank_details",
    "show_gst_summary",
    "show_hsn_sac",
    "show_signature",
    "show_terms",
    "show_payment_info",
    "show_page_numbers",
    "show_print_date",
    "print_on_letterhead"
]

for tmpl in sorted(templates):
    with open(os.path.join(templates_dir, tmpl)) as f:
        content = f.read()
        
    found = []
    for p in prefs:
        if re.search(r"prefs\." + p, content):
            found.append(p)
            
    print(f"{tmpl}: {', '.join(found) if found else 'NONE'}")
