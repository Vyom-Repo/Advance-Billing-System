import os
import django
import copy

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from weasyprint import HTML
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from apps.common.services.layout_engine import PrintableFrameBuilder

User = get_user_model()
user = User.objects.get(email='vyomprajapati149@gmail.com')

OUTPUT_DIR = '/Users/vyom/.gemini/antigravity-ide/brain/918ef134-b750-4417-aa55-878b4b12b092/scratch/test_matrix'
os.makedirs(OUTPUT_DIR, exist_ok=True)

base_context = InvoicePreviewService.get_preview_context(user)

def generate_pdf(case_name, context_overrides):
    context = copy.deepcopy(base_context)
    
    # Apply overrides
    for k, v in context_overrides.items():
        if isinstance(v, dict) and k in context and isinstance(context[k], dict):
            context[k].update(v)
        else:
            context[k] = v
            
    # Apply org properties if they were provided as dict in overrides
    if 'org_attrs' in context_overrides and context['org']:
        for attr, val in context_overrides['org_attrs'].items():
            setattr(context['org'], attr, val)
            
    if 'company' in context_overrides:
        context['company'].update(context_overrides['company'])

    # Rebuild the layout frame
    if isinstance(context['prefs'], dict):
        template_name = context['prefs'].get("template_name", "professional")
    else:
        template_name = getattr(context['prefs'], "template_name", "professional")
        
    context['layout_frame'] = PrintableFrameBuilder.build_frame(context.get('org'), context.get('prefs'))
    
    template_path = f"pdf/{template_name}.html"
    html_string = render_to_string(template_path, context)
    
    # We must use the exact same request URI generation method. For a script we use a dummy base url
    pdf_file = HTML(string=html_string, base_url="http://127.0.0.1:8000/").write_pdf()
    
    out_path = os.path.join(OUTPUT_DIR, f"{case_name}.pdf")
    with open(out_path, 'wb') as f:
        f.write(pdf_file)
    print(f"Generated {case_name}")

# Matrix Cases
# 1. No logo, No letterhead, No signature, No bank
generate_pdf("Case_1_Core_Simple", {
    "prefs": {
        "show_company_logo": False,
        "show_company_header": True,
        "print_on_letterhead": False,
        "show_signature": False,
        "show_bank_details": False
    },
    "org_attrs": {
        "letterhead": None
    }
})

# 2. Logo only
generate_pdf("Case_2_Logo_Only", {
    "prefs": {
        "show_company_logo": True,
        "show_company_header": True,
        "print_on_letterhead": False,
        "show_signature": False,
        "show_bank_details": False
    },
    "org_attrs": {
        "letterhead": None
    }
})

# 3. Letterhead only
generate_pdf("Case_3_Letterhead_Only", {
    "prefs": {
        "show_company_logo": False,
        "print_on_letterhead": True,
        "show_signature": False,
        "show_bank_details": False
    }
})

# 4. Letterhead + Logo
generate_pdf("Case_4_Letterhead_Logo", {
    "prefs": {
        "show_company_logo": True,
        "print_on_letterhead": True,
        "show_signature": False,
        "show_bank_details": False
    }
})

# 5. Letterhead + Signature
generate_pdf("Case_5_Letterhead_Signature", {
    "prefs": {
        "show_company_logo": False,
        "print_on_letterhead": True,
        "show_signature": True,
        "show_bank_details": False
    }
})

# 6. Letterhead + Bank Details
generate_pdf("Case_6_Letterhead_Bank", {
    "prefs": {
        "show_company_logo": False,
        "print_on_letterhead": True,
        "show_signature": False,
        "show_bank_details": True
    }
})

# 7. Letterhead + Everything
generate_pdf("Case_7_Letterhead_Everything", {
    "prefs": {
        "show_company_logo": True,
        "print_on_letterhead": True,
        "show_signature": True,
        "show_bank_details": True
    }
})

# 8. Large Header Offset
generate_pdf("Case_8_Large_Header_80mm", {
    "prefs": {
        "print_on_letterhead": True
    },
    "org_attrs": {
        "letterhead_header_offset": 80
    }
})

# 9. Small Header Offset
generate_pdf("Case_9_Small_Header_20mm", {
    "prefs": {
        "print_on_letterhead": True
    },
    "org_attrs": {
        "letterhead_header_offset": 20
    }
})

# 10. Large Footer Offset
generate_pdf("Case_10_Large_Footer_80mm", {
    "prefs": {
        "print_on_letterhead": True
    },
    "org_attrs": {
        "letterhead_footer_offset": 80
    }
})

# 11. Very Long Company Name
generate_pdf("Case_11_Long_Company_Name", {
    "company": {
        "name": "Strategic Legal Solutions International Private Limited"
    }
})

# 12. Very Long Address
generate_pdf("Case_12_Long_Address", {
    "company": {
        "address": "Floor 12, Tower B, Infinity IT Park\nBuilding No 9, Mindspace\nMalad West, Near Inorbit Mall\nMumbai City\nMaharashtra 400064, India"
    }
})

# 16. Twenty Invoice Items
items_20 = []
for i in range(20):
    items_20.append({"name": f"Consulting Service {i}", "hsn": "9983", "quantity": 1, "rate": 1000, "tax_pct": 18, "amount": 1000})

generate_pdf("Case_16_20_Items", {
    "items": items_20,
    "prefs": {
        "print_on_letterhead": True,
        "show_company_logo": False
    }
})

# 17. Fifty Invoice Items
items_50 = []
for i in range(50):
    items_50.append({"name": f"Bulk Item {i}", "hsn": "1234", "quantity": 1, "rate": 50, "tax_pct": 18, "amount": 50})

generate_pdf("Case_17_50_Items", {
    "items": items_50,
    "prefs": {
        "print_on_letterhead": True,
        "show_company_logo": False
    }
})

print("Matrix generation complete!")
