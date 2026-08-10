# TEMPLATE CONTENT MAP
An architectural and structural map of the current Advance Billing invoice rendering system.

## 1. UNDERSTANDING THE CURRENT TEMPLATE
The current template (`professional.html`) acts as the single source of truth for PDF generation via WeasyPrint. Below is a mapping of the major sections:

- **@page configuration**: Located in `<style>`, uses `layout_frame.paper_size` and `layout_frame.orientation` for the document dimensions. Defines page margins based on `layout_frame`.
- **letterhead background**: If `layout_frame.has_letterhead_background` is true, the `@page` directive applies `background-image: url("file://...")`, with `background-size: 100% 100%` forcing it full bleed.
- **page numbers**: Controlled by `prefs.show_page_numbers`. Implemented using `@bottom-right` CSS counter logic in the `@page` block.
- **body typography**: Handled by `prefs.font_size` which scales the root body font size (Small=10px, Normal=12px, Large=14px).
- **master spacer table**: A full-width `<table>` wrapping the entire `<body>`. Used solely to support multi-page letterhead spacing.
- **repeating header spacer**: A `<thead>` containing a blank `<tr><td>` with height set to `layout_frame.body_padding_top`. Because it is inside `<thead>`, WeasyPrint repeats this blank space on *every* page, preventing the invoice from overlapping the physical letterhead graphic.
- **repeating footer spacer**: A `<tfoot>` mirroring the header spacer using `layout_frame.body_padding_bottom`.
- **printable frame**: A wrapper div (`.printable-frame`) holding the actual invoice content.
- **standard company header**: Contains logo, company name, address, GSTIN, email, and phone. Controlled by `prefs.show_company_header` and `prefs.show_company_logo`. Disappears entirely in `letterhead_mode`.
- **letterhead mode header**: When `layout_frame.letterhead_mode` is true, only the invoice identification block (Title, No, Date, Due Date) is rendered right-aligned. The company branding is skipped since it is baked into the background image.
- **invoice identification block**: "INVOICE", Invoice No, Date, Due Date. Always displays.
- **company logo**: Depends on `prefs.show_company_logo` AND `org.logo` existing.
- **customer / billed-to section**: Shows `customer.name`, address, city, state, and optional `customer.gstin`.
- **invoice items table**: The core `<table>` for items. `page-break-inside: avoid` on `<tr>` prevents a row from being split across two pages.
- **HSN/SAC**: Column controlled by `prefs.show_hsn_sac`.
- **quantity, rate, amount**: Core columns, always rendered.
- **GST/tax percentage**: Controlled by `prefs.show_gst_summary`. Displays as `item.tax_pct`.
- **subtotal, total tax, grand total**: The totals block. `total tax` row is toggled by `prefs.show_gst_summary`.
- **bank details**: Controlled by `prefs.show_bank_details`. Expects `company.bank_name`, `company.acc_no`, `company.ifsc`.
- **notes**: Controlled by `invoice.notes`.
- **terms and conditions**: Controlled by `prefs.show_terms`. Currently hardcoded placeholder text: "Goods once sold will not be taken back."
- **signature**: Controlled by `prefs.show_signature`. Relies on `org.signature`. Renders the image if available and an "Authorized Signatory" line.
- **custom company footer**: Controlled by `prefs.show_company_footer`. Displays `prefs.custom_footer_message`.
- **print date**: Controlled by `prefs.show_print_date`. Uses Django's `{% now %}` tag.
- **QR section**: Controlled by `prefs.show_qr_code`. **CURRENTLY A PLACEHOLDER** (`<div class="qr-placeholder">QR Code</div>`). No real QR generation exists.

## 2. DATA MAP

### Company / Org
- **company.name**
  → source: `OrganizationService.get_company_assets` (from `Organization` model)
  → template: standard header
  → displayed as: Large bold text
  → required/optional: Required
- **company.address / city / state**
  → source: `OrganizationService`
  → template: standard header
  → required/optional: Required
- **company.gstin**
  → source: `OrganizationService`
  → template: standard header (conditional on existing)
  → displayed as: "GSTIN: [value]"
- **company.bank_name / acc_no / ifsc**
  → source: `OrganizationService` default bank relation
  → template: Bank details footer section
  → displayed as: Label: Value format
  → affected by: `prefs.show_bank_details`
- **org.logo**
  → source: `Organization` model `logo` ImageField
  → template: standard header
  → displayed as: `<img src="file://...">`
  → required/optional: Optional
  → affected by: `prefs.show_company_logo`
- **org.signature**
  → source: `Organization` model `signature` ImageField
  → template: Footer signature block
  → displayed as: `<img src="file://...">`
  → required/optional: Optional
  → affected by: `prefs.show_signature`
- **org.letterhead**
  → source: `Organization` model `letterhead` ImageField
  → template: Passed into `layout_frame.background_image_url`

### Invoice
- **invoice.number / date / due_date**
  → source: `SampleDataService` (currently mocked, represents future `Invoice` model)
  → template: Invoice identification block
  → required/optional: Required
- **invoice.subtotal / tax_total / total**
  → source: `SampleDataService`
  → template: Totals table
  → required/optional: Required
- **invoice.notes**
  → source: `SampleDataService`
  → template: Footer section
  → displayed as: Multi-line text (`linebreaksbr`)
  → affected by: Its own existence.

### Customer
- **customer.name / address / city / state**
  → source: `SampleDataService`
  → template: Billed To block
  → required/optional: Required
- **customer.gstin**
  → source: `SampleDataService`
  → template: Billed To block
  → required/optional: Optional

### Items (List)
- **item.name / quantity / rate / amount**
  → source: `SampleDataService`
  → template: Items table `<tbody>`
  → required/optional: Required
- **item.hsn**
  → affected by: `prefs.show_hsn_sac`
- **item.tax_pct**
  → affected by: `prefs.show_gst_summary`

### Preferences (prefs)
- **prefs.show_company_header**
  → source: `DocumentPreference`
  → template: Controls rendering of the entire left-hand company branding block.
- **prefs.show_company_logo**
  → template: Controls the logo `<img>` within the company header.
- **prefs.show_qr_code**
  → template: Controls the placeholder QR box.
- **prefs.show_hsn_sac**
  → template: Toggles the HSN/SAC `<th>` and `<td>`.
- **prefs.show_gst_summary**
  → template: Toggles the Tax % column and the "Total Tax" row in the totals.
- **prefs.show_bank_details**
  → template: Toggles the Bank Details footer block.
- **prefs.show_terms**
  → template: Toggles the Terms & Conditions block.
- **prefs.show_signature**
  → template: Toggles the signature block and image.
- **prefs.show_company_footer**
  → template: Toggles the entire bottom-most footer div.
- **prefs.custom_footer_message**
  → template: Renders the custom text inside the footer.
- **prefs.show_print_date**
  → template: Toggles the "Printed on [Date]" text.
- **prefs.show_page_numbers**
  → template: Generates `@bottom-right` CSS counter logic.
- **prefs.font_size / table_density**
  → template: Alters body `font-size` and table cell `padding`.

### Layout Frame (layout_frame)
- **paper_size / orientation / margin_* **
  → source: `PrintableFrameBuilder`
  → template: Populates the CSS `@page` rule.
- **letterhead_mode**
  → source: `PrintableFrameBuilder` (if `print_on_letterhead` and `org.letterhead` exists)
  → template: Disables the standard header, renders the master spacer table.
- **body_padding_top / body_padding_bottom**
  → source: Translated from `org.letterhead_header_offset` / `footer_offset`.
  → template: Sets the height of the `<thead>` and `<tfoot>` spacers.

## 3. TRACING EVERY TOGGLE

- **show_company_header**: 
  - OFF: The company name, address, phone, GSTIN, and logo disappear. The right-aligned Invoice block remains.
  - ON: The company details render, provided `layout_frame.letterhead_mode` is False. If `letterhead_mode` is True, this toggle is ignored entirely because the letterhead itself replaces the header.
- **show_company_logo**:
  - OFF: The logo image disappears.
  - ON: Logo renders ONLY IF `show_company_header` is True AND `org.logo` exists AND `letterhead_mode` is False.
- **show_qr_code**:
  - OFF: QR placeholder disappears.
  - ON: Placeholder `<div class="qr-placeholder">` appears in the header. (Not real QR).
- **show_hsn_sac**:
  - OFF: The table loses the HSN column.
  - ON: The HSN column appears.
- **show_gst_summary**:
  - OFF: The "Tax %" column in the items table disappears. The "Total Tax" row in the totals block disappears.
  - ON: Both appear. Note: This template currently does NOT have a CGST/SGST/IGST breakdown.
- **show_bank_details**:
  - OFF: Bank details block disappears.
  - ON: Appears in the left column of the footer.
- **show_terms**:
  - OFF: Terms block disappears.
  - ON: Appears in the left column of the footer (hardcoded placeholder text).
- **show_signature**:
  - OFF: Signature block disappears.
  - ON: Appears in the right column of the footer. Includes the `org.signature` image IF it exists, otherwise just the "Authorized Signatory" line.
- **show_company_footer**:
  - OFF: The bottom-most centered footer disappears.
  - ON: Appears, enabling `custom_footer_message` and `show_print_date`.
- **letterhead mode / print_on_letterhead**:
  - OFF: Standard mode. Page margins are applied (e.g. 15mm). No background image. Company header renders normally.
  - ON (and artwork exists): Full bleed `@page` configuration. Background image applied. Page margins set to 0. `master spacer table` activates `<thead>` and `<tfoot>` spacing to protect the letterhead design area. Standard company header is hidden.
- **header/footer offset**:
  - Becomes `layout_frame.body_padding_top` / `bottom`.
  - Determines the exact `height` of the `<thead>` and `<tfoot>` spacer rows.

## 4. SECTION PLACEMENT
In HTML/CSS (and WeasyPrint), placement is dictated by the document flow. 
- The **header** is at the top because it is the first block-level element in the `.printable-frame`.
- The **Billed To** section naturally flows below the header.
- The **items table** flows below the Billed To section.
- The **totals** appear below items. They are pushed to the right using `display: flex; justify-content: flex-end;` on the wrapper, and `float: right;` on the table.
- The **signature/footer** flows at the very bottom.
- The **letterhead** stays behind everything because it is applied to the `@page` background property, fundamentally separating it from the HTML DOM flow.
- **Header offset changes** move the content down because they increase the `height` of the `<thead>` element in the master spacer table. Since the `<tbody>` flows *after* the `<thead>`, all content is physically pushed down.
- **Page 2 continuation** works because the `<tbody>` automatically breaks across pages in standard HTML table rendering. Since the `<thead>` is instructed by WeasyPrint to repeat on every new page, the header offset is automatically applied again at the top of Page 2, protecting the letterhead artwork on the second page.
- **Table row splitting avoidance** is achieved via `page-break-inside: avoid;` on the `<tr>` elements.

## 5. LETTERHEAD ARCHITECTURE
- **Source**: Uploaded by the user into the `Organization` model (`org.letterhead`).
- **Layout Frame**: `PrintableFrameBuilder` detects `print_on_letterhead`. It creates a `file://` URL for WeasyPrint (WeasyPrint needs local absolute file paths, not web URLs, to resolve images securely and quickly).
- **@page**: It injects `background-image: url("file://...")` and sets all page margins to `0`. `background-size: 100% 100%` stretches it fully edge-to-edge.
- **Master Spacer Table**: Because the physical PDF page now has 0 margins (to allow edge-to-edge letterhead printing), we need artificial margins to prevent the text from overlapping the artwork.
- **<thead>**: We use a `<thead>` with a blank row set to `height: {{ layout_frame.body_padding_top }}`. When an HTML table crosses a page boundary, WeasyPrint repeats the `<thead>` at the top of the new page. This ingenious trick guarantees that the top offset is enforced on *every single page* of a multi-page invoice without complex coordinate math.
- **Diagram**:
```text
┌────────────────────────────────┐
│ @page background (full bleed)  │
│ ┌────────────────────────────┐ │
│ │ <thead> spacer (offset)    │ │
│ ├────────────────────────────┤ │
│ │                            │ │
│ │ <tbody>                    │ │
│ │ Invoice Content            │ │
│ │ (Flows onto multiple pages)│ │
│ │                            │ │
│ ├────────────────────────────┤ │
│ │ <tfoot> spacer (offset)    │ │
│ └────────────────────────────┘ │
└────────────────────────────────┘
```

## 6. STANDARD MODE VS LETTERHEAD MODE

**STANDARD MODE:**
- Page has standard CSS margins (15mm).
- No background image.
- `show_company_header` dictates if the software-generated Company Branding (Logo, Name, Address, GSTIN) renders.
- Invoice title, number, and date render alongside the company header.

**LETTERHEAD MODE:**
- Page has 0 margins.
- Background image is the uploaded physical letterhead.
- The software-generated Company Branding is COMPLETELY SUPPRESSED. The physical letterhead acts as the branding.
- Only the Invoice title, number, and date render (aligned to the right) to identify the document.

## 7. GST MAP
**A. GST Data:** Currently mocked in `SampleDataService`.
**B. GST Presentation:** 
- **GSTIN**: Rendered conditionally in the Billed To and Company Header blocks if the `gstin` variable exists.
- **HSN/SAC**: Rendered as a column if `prefs.show_hsn_sac` is true.
- **Tax %**: Rendered as a column (`item.tax_pct`) if `prefs.show_gst_summary` is true.
- **Total Tax**: Rendered as a row in the totals block if `prefs.show_gst_summary` is true.
- **DOES NOT EXIST**: The current template DOES NOT provide a CGST/SGST/IGST split or summary table. It only shows a flat Tax % per item and a grand Total Tax.

## 8. QR MAP
- **Toggle**: `prefs.show_qr_code`
- **Condition**: `{% if prefs.show_qr_code %}`
- **Generation/Source**: There is no actual QR code generation.
- **Status**: **PLACEHOLDER**. It renders a grey box `<div class="qr-placeholder">QR Code</div>`.

## 9. BRANDING MAP
- **Logo**: 
  - Source: `org.logo`
  - Toggle: `prefs.show_company_logo`
  - Mechanism: `<img src="file://...">` with `max-height: 60px; max-width: 200px;`
  - Dependency: Standard Mode only.
- **Company Header**:
  - Source: `company` dict
  - Toggle: `prefs.show_company_header`
  - Dependency: Standard Mode only.
- **Letterhead**:
  - Source: `org.letterhead`
  - Toggle: `print_on_letterhead`
  - Rendering: `@page` background image.
- **Signature**:
  - Source: `org.signature`
  - Toggle: `prefs.show_signature`
  - Mechanism: `<img src="file://...">` with `max-height: 50px; max-width: 150px;`
- **Footer**:
  - Source: `prefs.custom_footer_message`
  - Toggle: `prefs.show_company_footer`

## 10. PAGINATION MAP
- **page-break-inside**: Applied to `info-section`, `items-table tr`, `totals-section`, and `footer` to prevent these blocks from awkwardly splitting in half across a page boundary.
- **master table**: Wraps the entire body.
- **thead repetition**: Pushes content down past the letterhead header artwork on EVERY page.
- **tfoot repetition**: Pushes content up past the letterhead footer artwork on EVERY page.
- **long invoice behavior**: The `<tbody>` seamlessly flows onto page 2, 3, etc. WeasyPrint handles the page breaks automatically.

## 11. TEMPLATE COMPONENT TREE
```text
DOCUMENT
├── Page Configuration (@page, CSS)
├── Letterhead Layer (Background Image)
├── Master Spacer Table
│   ├── Thead (Header Offset Spacer)
│   ├── Tbody (Printable Frame)
│   │   ├── Header
│   │   │   ├── Standard Mode (Company Branding + Invoice Metadata)
│   │   │   └── Letterhead Mode (Invoice Metadata Only)
│   │   ├── Customer Information (Billed To)
│   │   ├── Items Table (with conditional HSN/GST columns)
│   │   ├── Totals Block (with conditional GST row)
│   │   ├── Secondary Footer
│   │   │   ├── Bank Details
│   │   │   ├── Notes
│   │   │   ├── Terms (Placeholder)
│   │   │   └── Signature
│   │   └── Document Footer (Custom text + Print Date)
│   └── Tfoot (Footer Offset Spacer)
```

## 12. DATA VS PRESENTATION
- **DATA**: `invoice.total`, `item.rate`, `company.name`. The business logic required to calculate or fetch these.
- **PRESENTATION**: Whether the `company.name` is bold (`font-weight: bold`), whether it is displayed at all (`prefs.show_company_header`), and where it is physically located (top left). 
The 10 future templates will share the exact same **DATA** (the `invoice_preview_service.py` context dictionary) but will completely replace the **PRESENTATION** (HTML/CSS).

## 13. CURRENT TEMPLATE CONTRACT
The `professional.html` template expects exactly:
- `company` dict (name, address, city, state, gstin, email, phone, bank details)
- `org` object (logo, signature, letterhead paths)
- `invoice` object (number, date, due_date, subtotal, tax_total, total, notes)
- `customer` object (name, address, city, state, gstin)
- `items` list of dicts (name, hsn, quantity, rate, tax_pct, amount)
- `prefs` dict (all UI toggles)
- `layout_frame` dict (all WeasyPrint page configurations)

## 14. EXISTING COMPONENTS VS MISSING COMPONENTS
**EXISTING (Genuinely Implemented):**
- Dynamic @page margins
- Letterhead full-bleed rendering
- Multi-page letterhead spacing
- Logo and Signature `file://` rendering
- Items table pagination
- Conditional GST/HSN columns
- Print Date (`{% now %}`)
- Font sizing (Small/Normal/Large)

**MISSING / PLACEHOLDER:**
- **QR Code**: Not implemented. Just a grey placeholder div.
- **Terms & Conditions**: Hardcoded text ("Goods once sold..."). Not data-driven.
- **GST Breakdown**: No CGST/SGST/IGST split. Only a flat "Total Tax" row exists.

## 15. TEMPLATE REUSE PRINCIPLE
Because all data gathering and `layout_frame` mathematics are abstracted into Python services (`InvoicePreviewService`, `PrintableFrameBuilder`), the Django context passed to the template is perfectly standardized.
To create a new template, we simply write a new HTML file (e.g., `minimal.html`). We can rearrange the HTML blocks (e.g., put Billed To on the right, Invoice Metadata on the left), change the fonts, change the colors, and it will instantly support all pagination, letterhead, and toggle logic without any backend modifications.
