# COMPONENT LABORATORY
This document is an educational laboratory guide for understanding the Advance Billing invoice rendering system. It explains how to test and observe the behavior of the current implementation.

## 1. COMPONENT LAB

| Component | Toggle | Data | Template Condition | Visible Result | Dependency |
|-----------|--------|------|--------------------|----------------|------------|
| Company Header | `show_company_header` | `company` dict | `{% if prefs.show_company_header %}` | Renders Left column branding | Fails if `letterhead_mode` is True |
| Company Logo | `show_company_logo` | `org.logo` | `{% if prefs.show_company_logo and org.logo %}` | Renders `<img class="logo">` | Requires `org.logo` |
| Invoice Metadata | N/A | `invoice` dict | Always renders | Renders right-aligned INVOICE title and metadata | None |
| Customer Block | N/A | `customer` dict | Always renders | Renders "Billed To" block | None |
| HSN/SAC | `show_hsn_sac` | `item.hsn` | `{% if prefs.show_hsn_sac %}` | Renders HSN/SAC column in items table | None |
| GST Summary | `show_gst_summary`| `item.tax_pct`, `invoice.tax_total` | `{% if prefs.show_gst_summary %}` | Renders Tax % column and Total Tax row | None |
| QR Code | `show_qr_code` | N/A | `{% if prefs.show_qr_code %}` | Renders a placeholder grey box | None (Placeholder only) |
| Bank Details | `show_bank_details` | `company.bank_name` etc | `{% if prefs.show_bank_details %}` | Renders left footer block | None |
| Notes | N/A | `invoice.notes` | `{% if invoice.notes %}` | Renders left footer block | Requires `invoice.notes` |
| Terms | `show_terms` | N/A | `{% if prefs.show_terms %}` | Renders left footer block | None (Hardcoded text) |
| Signature | `show_signature` | `org.signature` | `{% if prefs.show_signature %}` | Renders right footer block | Renders image ONLY if `org.signature` exists |
| Company Footer | `show_company_footer` | `prefs.custom_footer_message` | `{% if prefs.show_company_footer %}` | Renders bottom centered text | None |
| Print Date | `show_print_date` | `{% now %}` | `{% if prefs.show_print_date %}` | Renders "Printed on [Date]" | Requires `show_company_footer` |
| Page Numbers | `show_page_numbers` | CSS Counters | `{% if prefs.show_page_numbers %}` | `@bottom-right` page counters | None |
| Letterhead | `print_on_letterhead`| `org.letterhead` | `@page` CSS Background | Full bleed background image | Requires `org.letterhead` |

## 2. TOGGLE EXPERIMENTS

**Experiment: Turn `show_gst_summary` OFF**
- Expected: The "Tax %" column disappears from the items table. The "Total Tax" row disappears from the totals block.

**Experiment: Turn `show_company_header` OFF**
- Expected: The company name, address, email, and phone disappear. The invoice metadata block shifts to the right.

**Experiment: Turn `print_on_letterhead` ON**
- Expected: The software-generated company header disappears completely. The background image fills the entire PDF page. The master spacer table pushes the content down to respect the artwork.

## 3. COMPONENT DEPENDENCY LAB

- `show_signature` + `org.signature` exists = Signature image rendered + "Authorized Signatory".
- `show_signature` + `org.signature` missing = Only "Authorized Signatory" text rendered.
- `show_company_logo` + `org.logo` exists = Logo rendered.
- `print_on_letterhead` + `org.letterhead` uploaded = Letterhead mode activates (background rendered, header suppressed).
- `print_on_letterhead` + `org.letterhead` missing = Falls back to standard mode automatically.

## 4. POSITIONING LAB

**Experiment:** Change header offset (e.g. 30mm → 50mm → 80mm).
**Observation:** 
- The Billed To section, invoice metadata, and item table physically move down the page.
- Page 2 content also moves down exactly the same amount.
**Mechanism:** The `org.letterhead_header_offset` is translated into `layout_frame.body_padding_top`. This height is applied to a blank `<tr>` inside the `<thead>` of a master wrapper `<table>`. WeasyPrint automatically repeats `<thead>` elements at the top of every new page, applying the exact offset spacing on all pages.

## 5. LETTERHEAD LAB

1. **Standard mode**: Observe standard margins and software-generated branding.
2. **Enable letterhead**: Branding vanishes. Background artwork appears. Margins vanish (full bleed).
3. **Change header offset**: The invisible `<thead>` spacer grows, pushing the start of the invoice text down.
4. **Change footer offset**: The invisible `<tfoot>` spacer grows, pushing the end of the invoice text up.
5. **Generate multi-page invoice**: Add 50 items.
6. **Observe page 2**: Notice the letterhead repeats perfectly, and the text begins exactly at the header offset again.
7. **Compare with downloaded PDF**: Identical.

## 6. GST LAB

- **GST OFF**: Items table has 4 columns (Description, Qty, Rate, Amount). Totals have Subtotal and Total.
- **GST ON**: Items table has 5 columns (adds Tax %). Totals has 3 rows (adds Total Tax).
- **HSN ON**: Items table has 6 columns (adds HSN/SAC).
- **Presentation vs Data**: The template simply toggles the HTML columns based on the preference. It does not perform any math. The math is provided by the backend (`invoice.tax_total`).

## 7. QR LAB

- **Observation**: When `show_qr_code` is toggled ON, the UI displays a grey square box with the text "QR Code". 
- **Conclusion**: This is purely a visual **PLACEHOLDER**. No actual QR code is being generated or rendered in the current system. 

## 8. BRANDING LAB

- **Logo OFF**: Logo img tag removed from HTML.
- **Header OFF**: Entire left branding div removed.
- **Letterhead ON**: Background artwork replaces all software headers.
- **Signature OFF**: Bottom right authorized signatory block disappears.

## 9. PAGINATION LAB

- **1 item**: Fits cleanly on one page. `<tfoot>` pushes footer up if in letterhead mode.
- **50+ items**: The `<tbody>` of the items table overflows the page height. WeasyPrint automatically breaks the table and continues it on the next page.
- **table behavior**: `page-break-inside: avoid` on `<tr>` ensures a single item row is never sliced horizontally in half.
- **totals behavior**: The `totals-section` has `page-break-inside: avoid`, ensuring the subtotal and grand total always appear together on the same page.

## 10. TEMPLATE COMPARISON PREPARATION

Because all toggles are driven by the standardized `prefs` context, and all data by `invoice`/`company`, we can safely rearrange the layout without breaking the logic.
- **Template A**: Standard layout.
- **Template B**: We could move `{% if prefs.show_company_logo %}` to the center of the page, and the `Billed To` section to the right. 
The backend does not care where the template renders the logo, only *that* it passes the `org` object.

## 11. TEN-TEMPLATE PREPARATION

When creating 10 templates, the following must remain **STABLE**:
- `InvoicePreviewService` context generation.
- `PrintableFrameBuilder` layout calculation (`layout_frame`).
- Database models and preference toggles.

The following will be **VARIABLE**:
- HTML structure (`<table>` vs `<div>` layouts).
- CSS classes, colors, fonts, and borders.
- The physical order of the components (e.g. Billed To on the left vs right).

We MUST NOT duplicate the backend logic across templates. All 10 templates will consume the exact same `context` dictionary.

## 12. COMPONENT LAB CHECKLIST

- [x] Company Header understood
- [x] Logo understood
- [x] Letterhead understood
- [x] Invoice metadata understood
- [x] Customer section understood
- [x] Items understood
- [x] HSN/SAC understood
- [x] GST understood
- [x] QR understood (Placeholder verified)
- [x] Totals understood
- [x] Bank details understood
- [x] Notes understood
- [x] Terms understood (Placeholder verified)
- [x] Signature understood
- [x] Footer understood
- [x] Page numbers understood
- [x] Pagination understood
- [x] Header offset understood
- [x] Footer offset understood
- [x] Standard vs letterhead mode understood
