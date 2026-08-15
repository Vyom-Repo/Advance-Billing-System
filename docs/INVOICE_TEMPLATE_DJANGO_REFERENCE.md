# Django Invoice Template Tag & Variable Reference

## 1. Django Template Syntax

This section documents the Django template constructs supported by this project (Django).
*Note: While these are valid constructs, inspection of the current `templates/pdf/*.html` files reveals they are currently completely static mockups. No Django variables or conditional blocks are actively used in the templates.*

### Variable Output
```django
{{ variable }}
{{ object.field }}
{{ object.nested.field }}
```

### Conditional Blocks
```django
{% if condition %}
{% endif %}

{% if condition %}
{% else %}
{% endif %}

{% if condition %}
{% elif other_condition %}
{% else %}
{% endif %}
```

### Loops
```django
{% for item in items %}
{% endfor %}
```
Inside a loop, you can use:
- `{{ forloop.counter }}`
- `{{ forloop.counter0 }}`
- `{{ forloop.revcounter }}`
- `{{ forloop.revcounter0 }}`
- `{{ forloop.first }}`
- `{{ forloop.last }}`
- `{{ forloop.parentloop }}`

---

## 2. Django Filters

### A. Filters actually used by current templates
**NONE**. The current PDF templates are completely static HTML files and use no Django filters.

### B. Standard Django filters that are safe/useful for invoice templates
- `|default`: Fallback if a value is falsy. `{{ invoice.notes|default:"No notes" }}`
- `|default_if_none`: Fallback if exactly None. `{{ company.email|default_if_none:"" }}`
- `|length`: Returns the length of a list. `{{ items|length }}`
- `|lower` / `|upper` / `|title`: String casing. `{{ customer.name|upper }}`
- `|date`: Date formatting. `{{ invoice.date|date:"d M Y" }}`
- `|floatformat`: Formats floats to decimal places. `{{ item.amount|floatformat:2 }}`
- `|add`: Adds or subtracts. `{{ invoice.subtotal|add:invoice.tax_total }}`
- `|safe`: Marks a string as not requiring HTML escaping.
- `|escape`: Escapes HTML.
- `|linebreaksbr`: Converts newlines to `<br>`. Very useful for addresses and notes. `{{ invoice.notes|linebreaksbr }}`

---

## 3. Project-Specific Template Context

The context is built and injected via `apps/invoices/services/invoice_preview_service.py` (`InvoicePreviewService.get_preview_context`).

The following context keys are confirmed to be passed to `render_to_string`:

| Context Key    | Python Source                  | Type | Description                                        | Can be None? | Template Usage |
|----------------|--------------------------------|------|----------------------------------------------------|--------------|----------------|
| `invoice`      | `SampleDataService.sample_invoice` | dict | Invoice metadata (number, dates, totals, notes).   | No           | UNCONFIRMED    |
| `customer`     | `SampleDataService.sample_customer`| dict | Customer details.                                  | No           | UNCONFIRMED    |
| `items`        | `SampleDataService.sample_items`   | list | List of line item dicts.                           | No           | UNCONFIRMED    |
| `company`      | `OrganizationService.get_company_assets` | dict | Company branding and details.                      | No           | UNCONFIRMED    |
| `org`          | `Organization` model           | obj  | The actual Organization instance.                  | Yes (demo)   | UNCONFIRMED    |
| `prefs`        | `DocumentPreference` model     | dict/obj | User preferences for layout and toggles.           | No           | UNCONFIRMED    |
| `layout_frame` | `PrintableFrameBuilder.build_frame`| dict | Geometry settings for printing (`@page`, margins). | No           | UNCONFIRMED    |

*Important Note: Context is identical for Demo (Test PDF) and Production mode, except that in Demo mode `org` is `None` and `company` is populated via `SampleDataService.sample_company()`.*

---

## 4. COMPANY / ORGANIZATION DATA

The `company` dictionary is built in `InvoicePreviewService.get_preview_context`.

| Template expression | Confirmed? | Source | Description | Nullable? |
| ------------------- | ---------- | ------ | ----------- | --------- |
| `{{ company.name }}` | YES | `Organization.business_name` | The company name | No |
| `{{ company.address }}` | YES | `Organization.address_line_1/2` | Merged address lines | No |
| `{{ company.city }}` | YES | `Organization.city` | Company city | No |
| `{{ company.state }}` | YES | `Organization.state` | Company state | No |
| `{{ company.gstin }}` | YES | `Organization.gstin` | Company GSTIN | Yes |
| `{{ company.email }}` | YES | `Organization.email` | Company email | Yes |
| `{{ company.phone }}` | YES | `Organization.phone` | Company phone | Yes |
| `{{ company.logo_url }}` | YES | `Organization.logo.path` | Absolute `file://` path to logo | Yes |
| `{{ company.signature_url }}`| YES | `Organization.signature.path`| Absolute `file://` path to signature | Yes |
| `{{ company.letterhead_url }}`| YES | `Organization.letterhead.path`| Absolute `file://` path to letterhead | Yes |
| `{{ company.bank_name }}` | YES | `BankDetails.bank_name` | Default bank name | Yes |
| `{{ company.acc_no }}` | YES | `BankDetails.account_number` | Default bank account number | Yes |
| `{{ company.ifsc }}` | YES | `BankDetails.ifsc_code` | Default bank IFSC | Yes |

*Template Usage: UNCONFIRMED in `templates/pdf/*.html`.*

---

## 5. CUSTOMER DATA

The `customer` dictionary is built by `SampleDataService.sample_customer()`.

| Template expression | Confirmed? | Description |
| ------------------- | ---------- | ----------- |
| `{{ customer.name }}` | YES | Customer name |
| `{{ customer.address }}`| YES | Street address |
| `{{ customer.city }}` | YES | City |
| `{{ customer.state }}` | YES | State |
| `{{ customer.gstin }}` | YES | GSTIN number |

*Template Usage: UNCONFIRMED in `templates/pdf/*.html`.*

---

## 6. INVOICE DATA

The `invoice` dictionary is built by `SampleDataService.sample_invoice()`.

| Template expression | Confirmed? | Description |
| ------------------- | ---------- | ----------- |
| `{{ invoice.number }}` | YES | Formatted invoice number |
| `{{ invoice.date }}` | YES | Issue date |
| `{{ invoice.due_date }}`| YES | Due date |
| `{{ invoice.subtotal }}`| YES | Total before tax |
| `{{ invoice.tax_total }}`| YES | Total tax amount |
| `{{ invoice.total }}` | YES | Grand total |
| `{{ invoice.notes }}` | YES | Invoice notes |
| `{{ invoice.terms }}` | YES | Invoice terms and conditions |
| `{{ invoice.currency }}`| YES | e.g. "INR", "USD" |
| `{{ invoice.qr_code_url }}`| YES | `file://` path to QR code |

*Template Usage: UNCONFIRMED in `templates/pdf/*.html`.*

---

## 7. LINE ITEMS

The `items` list is built by `SampleDataService.sample_items()`.

Iteration: `{% for item in items %}`

| Template expression | Confirmed? | Description |
| ------------------- | ---------- | ----------- |
| `{{ item.name }}` | YES | Item name/description |
| `{{ item.hsn }}` | YES | HSN/SAC code |
| `{{ item.quantity }}` | YES | Quantity |
| `{{ item.rate }}` | YES | Unit rate |
| `{{ item.tax_pct }}` | YES | Tax percentage (e.g. 18) |
| `{{ item.amount }}` | YES | Total line amount |

*Template Usage: UNCONFIRMED in `templates/pdf/*.html`.*

---

## 8. PREFERENCES

The `DocumentPreference` model defines toggles and layout preferences, passed via `prefs`.

| Preference | Type | Default | UI Source | Template Usage | Notes |
| ---------- | ---- | ------- | --------- | -------------- | ----- |
| `{{ prefs.show_company_logo }}` | Bool | True | Settings | UNCONFIRMED | Displays logo |
| `{{ prefs.show_company_header }}` | Bool | True | Settings | UNCONFIRMED | Displays full company address block |
| `{{ prefs.show_company_footer }}` | Bool | True | Settings | UNCONFIRMED | Displays standard footer |
| `{{ prefs.print_on_letterhead }}` | Bool | False | Settings | UNCONFIRMED | Hides header/footer for pre-printed stationery |
| `{{ prefs.show_qr_code }}` | Bool | True | Settings | UNCONFIRMED | Displays QR code |
| `{{ prefs.show_bank_details }}` | Bool | True | Settings | UNCONFIRMED | Displays Bank block |
| `{{ prefs.show_gst_summary }}` | Bool | True | Settings | UNCONFIRMED | Displays tax columns/totals |
| `{{ prefs.show_hsn_sac }}` | Bool | True | Settings | UNCONFIRMED | Displays HSN column |
| `{{ prefs.show_signature }}` | Bool | True | Settings | UNCONFIRMED | Displays auth signature |
| `{{ prefs.show_terms }}` | Bool | True | Settings | UNCONFIRMED | Displays terms block |
| `{{ prefs.show_payment_info }}` | Bool | True | Settings | UNCONFIRMED | Displays payment block |
| `{{ prefs.show_page_numbers }}` | Bool | True | Settings | UNCONFIRMED | Generates CSS `@bottom-right` logic |
| `{{ prefs.show_print_date }}` | Bool | True | Settings | UNCONFIRMED | Displays "Printed on..." |
| `{{ prefs.template_name }}` | Str | 'gst_classic'| Settings | UNCONFIRMED | Current selected template |
| `{{ prefs.paper_size }}` | Str | 'A4' | Settings | UNCONFIRMED | A4 or Letter |
| `{{ prefs.orientation }}` | Str | 'Portrait'| Settings | UNCONFIRMED | Portrait or Landscape |
| `{{ prefs.margins }}` | Str | 'Normal' | Settings | UNCONFIRMED | Narrow, Normal, Wide |
| `{{ prefs.font_size }}` | Str | 'Medium' | Settings | UNCONFIRMED | Small, Medium, Large |
| `{{ prefs.table_density }}` | Str | 'Comfortable'| Settings | UNCONFIRMED | Compact or Comfortable |
| `{{ prefs.custom_footer_message }}`| Str | (Text)| Settings | UNCONFIRMED | Message at bottom of invoice |

---

## 9. CONDITIONAL PREFERENCE PATTERNS

**Important Architectural Rule**: A template must not assume that an element exists simply because another template contains it. The preference represents semantic intent; each template controls its own geometry.

*Note: Since the templates are currently completely static, the patterns below are intended for future implementation.*

```django
{% if prefs.show_qr_code %}
    <img src="{{ invoice.qr_code_url }}">
{% endif %}

{% if prefs.show_gst_summary %}
    <td>{{ item.tax_pct }}%</td>
{% endif %}
```

---

## 10. LAYOUT FRAME / PRINTING GEOMETRY

The `layout_frame` is created by `PrintableFrameBuilder.build_frame`.

| Template expression | Confirmed? | Description |
| ------------------- | ---------- | ----------- |
| `{{ layout_frame.has_letterhead_background }}`| YES | True if letterhead mode and artwork exists. |
| `{{ layout_frame.background_image_url }}`| YES | Absolute `file://` path to letterhead artwork. |
| `{{ layout_frame.paper_size }}`| YES | "A4" or "Letter". |
| `{{ layout_frame.orientation }}`| YES | "Portrait" or "Landscape". |
| `{{ layout_frame.margin_top/bottom/left/right }}`| YES | "15mm" (Standard) or "0" (Letterhead). |
| `{{ layout_frame.body_padding_top/bottom }}`| YES | mm spacing offset for letterhead (`<thead>`/`<tfoot>`). |
| `{{ layout_frame.body_padding_left/right }}`| YES | "15mm" padding used in letterhead mode. |
| `{{ layout_frame.letterhead_mode }}`| YES | Boolean indicating if layout is in letterhead mode. |

**Geometry Impact**: In letterhead mode, margins are zeroed out so the background image covers the whole page, and the `body_padding_*` values are used to construct invisible `<thead>`/`<tfoot>` spacer rows.

---

## 11. TEMPLATE-SPECIFIC DJANGO LOGIC

*Every production PDF template in `templates/pdf/` was inspected. The results are identical across the board.*

### Template name
All 12 templates (`professional_template.html`, `modern_template.html`, `genz.html`, `vintage.html`, etc.)

### Django variables used
UNCONFIRMED. No Django variables (`{{...}}`) are present. Data is hardcoded (e.g., "Marico Limited", "Rohan Sharma").

### Django conditionals
UNCONFIRMED. No Django conditional blocks (`{% if %}`) are present.

### Loops
UNCONFIRMED. No Django loops (`{% for %}`) are present.

### Special template-specific context
None found.

### Important layout dependency
None found (static HTML).

---

## 12. COMPLETE TEMPLATE CAPABILITY MATRIX

| Template | QR | GST | HSN/SAC | Payment | Bank | Signature | Terms | Page Numbers | Print Date |
| -------- | -- | --- | ------- | ------- | ---- | --------- | ----- | ------------ | ---------- |
| professional_template | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| modern_template | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| genz | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| compact_template | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| landscape_template | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| mrp_discount_template | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| service_template | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| vintage | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| evergreen | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| flipkart_invoice | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| gst_classic | NO | NO | NO | NO | NO | NO | NO | NO | NO |
| retail_gst_compact | NO | NO | NO | NO | NO | NO | NO | NO | NO |

*(Note: "NO" means explicitly NOT implemented dynamically, since templates are fully static mockups.)*

---

## 13. Rules for AI When Modifying a Production Invoice Template

1. Never modify `templates/reference/`.
2. Preserve all existing Django variables (once implemented).
3. Preserve all required `{% if %}` blocks.
4. Preserve loops.
5. Preserve the context contract.
6. Do not replace dynamic values with hardcoded sample data.
7. Do not copy static reference HTML directly over the production template.
8. Reference templates are visual specifications only.
9. Keep template-specific geometry inside the template.
10. Do not introduce a separate rendering engine for each template unless explicitly approved.
11. Do not change the shared preview pipeline merely to modify visual layout.
12. Validate the template with Django's template engine after modification (`validate_templates.py`).
13. Generate a real PDF with WeasyPrint after modification (`test_matrix.py` / `test_weasyprint.py`).
14. Compare the resulting PDF against the corresponding reference design.
15. Preserve all existing preference semantics.

---

## 14. STANDARD VS PROJECT-SPECIFIC SYNTAX

### Standard Django
Standard Django syntax refers to the built-in templating features of the Django framework.
```django
{{ variable }}
{% if condition %}
{% for item in list %}
{% with var=val %}
{% include "partial.html" %}
{% comment %}
```

### Project-Specific
Project-specific syntax relies on the context contract explicitly provided by `InvoicePreviewService` in this application.
```django
{{ company.name }}
{{ customer.gstin }}
{{ invoice.total }}
{{ prefs.show_qr_code }}
{{ layout_frame.paper_size }}
```
*These project-specific variables are guaranteed to exist by the Python backend architecture (once they are actually wired into the template).*

---

## 15. DO NOT CLAIM SUPPORT WITHOUT EVIDENCE
Every project-specific variable documented in Sections 3-10 has been confirmed to exist in the Python source code (`InvoicePreviewService`, `SampleDataService`, `layout_engine.py`, etc.), and is passed directly to the `render_to_string` context. 

However, they are officially **UNCONFIRMED** regarding template usage, because inspection of `templates/pdf/*.html` proves that none of the templates currently consume them (they are static mockups).

---

# AI HANDOFF: HOW TO SAFELY WORK WITH THESE TEMPLATES

### The Rendering Pipeline

```text
Reference HTML
    ↓
Visual source of truth
    ↓
Production Django template
    ↓
Dynamic project context
    ↓
Django template rendering
    ↓
HTML/CSS
    ↓
WeasyPrint
    ↓
PDF
```

### Architectural Principle
**ONE SHARED RENDERING PIPELINE + TEMPLATE-SPECIFIC HTML/CSS GEOMETRY + SHARED DATA CONTRACT + SHARED PREFERENCE SEMANTICS**

The system employs a single `InvoicePreviewService` to construct a unified data context. All 12 PDF templates share this identical context dictionary. There is absolutely no need to write a separate rendering engine, a separate view, or a separate context-builder for each template. To change how a template looks, or how it responds to a preference toggle, modify the HTML/CSS inside that specific template file in `templates/pdf/`. 

*Current State Advisory: The templates in `templates/pdf/` are currently static HTML mockups containing no Django variables. Phase C will likely involve converting these mockups to use the Django variables documented in this file.*
