import os
import django
from django.template import loader
from django.template.exceptions import TemplateSyntaxError, TemplateDoesNotExist

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings.development')
django.setup()

templates_dir = 'pdf'
template_files = [
    'compact_template.html',
    'evergreen.html',
    'flipkart_invoice.html',
    'genz.html',
    'gst_classic.html',
    'landscape_template.html',
    'modern_template.html',
    'mrp_discount_template.html',
    'professional_template.html',
    'retail_gst_compact.html',
    'service_template.html',
    'vintage.html'
]

print("=== TEMPLATE SYNTAX VALIDATION ===")
all_valid = True
for filename in template_files:
    template_path = f"{templates_dir}/{filename}"
    try:
        loader.get_template(template_path)
        print(f"[OK] {filename}")
    except TemplateSyntaxError as e:
        print(f"[SYNTAX ERROR] {filename}: {e}")
        all_valid = False
    except TemplateDoesNotExist as e:
        print(f"[MISSING ERROR] {filename}: {e}")
        all_valid = False
    except Exception as e:
        import traceback
        print(f"[OTHER ERROR] {filename}:")
        traceback.print_exc()
        all_valid = False

if all_valid:
    print("\nAll templates validated successfully.")
else:
    print("\nSome templates have errors.")
