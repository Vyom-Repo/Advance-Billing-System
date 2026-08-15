# templates/pdf/ — Bill Template Architecture

This directory contains the 8 hand-designed HTML/CSS bill/invoice PDF templates
for the Advance Billing application. Each template is rendered by WeasyPrint into
a PDF and served to the user.

---

## Architecture Overview

```
                ┌─────────────────────────────────────┐
                │           Django View                │
                │ (SettingsInvoiceDesignPreviewAPIView) │
                └───────────────┬─────────────────────┘
                                │
                     ┌──────────▼──────────┐
                     │  resolve_render_config  │
                     │ (5-layer config merge)  │
                     └──────────┬──────────┘
                                │ config dict
                     ┌──────────▼──────────┐
                     │  serialize_bill_for_render │
                     │  (canonical Bill dict)     │
                     └──────────┬──────────┘
                                │ bill, company, customer, items, gst_summary
                     ┌──────────▼──────────┐
                     │   render_bill_pdf    │
                     │  (single entry point) │
                     └──────────┬──────────┘
                                │ template_file_path
                     ┌──────────▼──────────┐
                     │  One of 8 templates  │
                     │  (this directory)    │
                     └──────────┬──────────┘
                                │ HTML string
                     ┌──────────▼──────────┐
                     │     WeasyPrint       │
                     │   → PDF bytes        │
                     └─────────────────────┘
```

---

## Templates in This Directory

| File | Slug | Orientation | Distinguishing Feature |
|---|---|---|---|
| `compact_template.html` | `compact_template` | Portrait | Integrated GST summary table, dispatch-from support |
| `genz.html` | `genz` | Portrait | Blue brand bar, meta-cell grid |
| `landscape_template.html` | `landscape_template` | **Landscape** | Full CGST/SGST breakdown table |
| `modern_template.html` | `modern_template` | Portrait | 3-column info-box header |
| `mrp_discount_template.html` | `mrp_discount_template` | Portrait | MRP + Selling Price + Discount columns |
| `professional_template.html` | `professional_template` | Portrait | Bill-To / Ship-To grid, receiver signature line |
| `service_template.html` | `service_template` | Portrait | Simplified: description + amount only (no qty/rate) |
| `vintage.html` | `vintage` | Portrait | Absolute-positioned invoice-in-a-frame with GST table |

---

## Template Context Contract

Every template receives exactly this context. **No template should add its own
data-fetching logic** — all data comes from the pipeline.

```python
{
    # Bill metadata
    "bill": {
        "number", "date", "due_date", "place_of_supply",
        "currency", "currency_symbol",
        "subtotal", "tax_total", "discount_total",
        "grand_total", "amount_payable", "amount_paid", "amount_due",
        "amount_in_words", "notes", "terms", "qr_code_url",
        "payment_method", "payment_date",
    },

    # Company / seller
    "company": {
        "name", "legal_name", "gstin", "pan", "state_code",
        "address", "city", "state", "pincode", "country",
        "email", "phone", "website",
        "logo_url",        # file:// URL for WeasyPrint <img src>
        "signature_url",   # file:// URL
        "letterhead_url",  # file:// URL
        "bank_name", "acc_no", "ifsc", "acc_name", "branch", "upi_id",
    },

    # Customer / buyer
    "customer": {
        "name", "gstin", "phone", "email",
        "address", "city", "state", "pincode", "state_code",
        "shipping_name", "shipping_address", "shipping_city",
        "shipping_state", "shipping_pincode",
    },

    # Line items
    "items": [{
        "index", "name", "description", "hsn",
        "quantity", "unit", "rate",
        "mrp", "discount", "discount_pct", "selling_price",  # optional (None if N/A)
        "tax_pct", "taxable_value", "tax_amount", "amount",
        "sub_items", "image_urls",  # optional lists
    }],

    # Per-HSN GST breakdown rows
    "gst_summary": [{
        "hsn", "tax_pct", "taxable",
        "cgst_rate", "cgst_amount",
        "sgst_rate", "sgst_amount",
        "igst_rate", "igst_amount",
        "total_tax",
        "is_total",  # True for the TOTAL row
    }],

    # Config / preference toggles (merged from BillTemplate + user prefs + request)
    "config": {
        # Visibility toggles
        "show_company_header", "show_company_logo", "show_company_footer",
        "print_on_letterhead",
        "show_qr_code", "show_bank_details", "show_gst_summary", "show_hsn_sac",
        "show_signature", "show_terms", "show_payment_info",
        "show_page_numbers", "show_print_date",
        "custom_footer_message",
        # Style
        "font_size", "table_density", "paper_size", "orientation", "margins",
        # Capability flags (template declares True/False in BillTemplate.default_config)
        "has_qr", "has_signature", "has_logo", "has_bank_details",
        "has_gst_summary", "has_hsn_sac", "has_tax_summary_table",
        "has_mrp_column", "has_selling_price_column",
        "has_product_images", "has_description_column",
        "has_receiver_signature", "has_dispatch_from",
        "simplified_items",
    },

    # WeasyPrint page geometry
    "layout_frame": { ... },

    # ORM Organization instance (for any extra attribute access)
    "org": <Organization instance or None>,
}
```

---

## Config Resolution Order (highest wins)

1. `_GLOBAL_DEFAULTS` (hardcoded in `invoice_preview_service.py`)
2. `BillTemplate.default_config` — template declares its capabilities
3. `DocumentPreference` model — user's global settings (paper_size, font, toggles)
4. `UserBillPreference.pref_overrides` — per-user, per-template overrides
5. Request-time overrides — one-off overrides from the UI (not persisted)

Unknown keys are silently dropped at layers 4 and 5 to prevent templates from receiving config they don't understand.

---

## How to Add a 13th Template

### 1. Create the HTML file

```
templates/pdf/my_new_template.html
```

- Receive ALL data via `{{ bill.xxx }}`, `{{ company.xxx }}`, `{% for item in items %}`, `{{ config.xxx }}`
- Do NOT hardcode any business data
- For optional sections, gate them with `{% if config.show_signature %}` etc.
- For template-specific extras, check `{% if config.has_my_feature %}`

### 2. Declare the template in DocumentPreference choices

```python
# apps/settings_app/models.py → DocumentPreference.TEMPLATE_CHOICES
("my_new_template", "My New Template"),
```

### 3. Run the seed command (or add a row to TEMPLATES in seed_bill_templates.py)

```python
# In seed_bill_templates.py TEMPLATES list:
{
    "slug":               "my_new_template",
    "name":               "My New Template",
    "description":        "...",
    "template_file_path": "pdf/my_new_template.html",
    "default_config": {
        # Standard keys
        "paper_size": "A4", "orientation": "Portrait", ...
        # Template-specific capabilities
        "has_my_feature": True,
    },
},
```

Then run:
```bash
python manage.py seed_bill_templates
```

### 4. Visual QA

```bash
python manage.py preview_bill_template my_new_template --output /tmp/my_new_preview.pdf
open /tmp/my_new_preview.pdf
```

---

## How to Add a New Config Toggle

1. Add the key to `_GLOBAL_DEFAULTS` in `invoice_preview_service.py`
2. Add the field to `DocumentPreference` model (and create a migration)
3. Add the field to `DocumentPreferenceForm`
4. Update `_merge_doc_prefs()` in `invoice_preview_service.py`
5. Add `{% if config.show_my_new_toggle %}` to any templates that support it
6. Add `"show_my_new_toggle": True/False` to `default_config` in `seed_bill_templates.py` for each template
7. Run `python manage.py seed_bill_templates --force` to update configs

---

## Visual QA Commands

```bash
# Preview a specific template (sample data)
python manage.py preview_bill_template compact_template
python manage.py preview_bill_template vintage --output /tmp/vintage.pdf

# Preview with a real user's org data
python manage.py preview_bill_template genz --user user@example.com

# Seed the BillTemplate table
python manage.py seed_bill_templates

# Force-overwrite template configs after updates
python manage.py seed_bill_templates --force
```
