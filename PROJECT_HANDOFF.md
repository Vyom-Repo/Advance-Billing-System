# Project Handoff & Architecture Context

## 1. Project Context
Advance Billing System is a Django-based application designed for generating and managing invoices. The current phase involves building a robust, highly customizable Invoice Design Feature that allows users to generate professional PDFs with various aesthetic themes, toggles, and physical letterhead support.

## 2. Invoice Design Feature
The feature provides a unified interface for users to select different invoice templates (e.g., Professional, Modern, Vintage) and customize them using granular preferences (toggling company header, GST summaries, bank details, QR codes, signatures, etc.). It must flawlessly translate these preferences into paginated, print-ready PDF documents.

## 3. Template Architecture
The system uses Django HTML templates as the layout engine. A single, standardized Python context dictionary (containing company data, mock invoice data, item lists, and preference settings) is injected into the templates. The templates contain the logical conditions (`{% if prefs.show_gst_summary %}`) and styling. 

## 4. Reference Template Architecture
Located in `templates/reference/`, these templates are designed for browser-based HTML preview. They represent how the invoice should look conceptually. They are optimized for web rendering and do not contain WeasyPrint-specific hacks, making them ideal for quick UI previews in the browser.

## 5. Production PDF Template Architecture
Located in `templates/pdf/`, these are the actual templates fed into WeasyPrint to generate the final PDF. They are structurally distinct from the reference templates. They utilize `@page` CSS directives, table-based layouts for guaranteed pagination (`page-break-inside: avoid`), absolute `file://` URIs for local image rendering, and a specialized master spacer table with `<thead>`/`<tfoot>` to support multi-page physical letterhead offsets.

## 6. Template Inventory
The system currently supports 10 distinct template designs:
1. Professional
2. Modern
3. Compact
4. Landscape
5. Vintage
6. Service
7. MRP Discount
8. Genz
9. Evergreen
10. Flipkart/GST Classic / Retail (Various regional formats)

## 7. Preference System
The `DocumentPreference` model controls the visual output. It contains:
- Boolean toggles: `show_company_header`, `show_company_logo`, `show_gst_summary`, `show_hsn_sac`, `show_qr_code`, `show_bank_details`, `show_terms`, `show_signature`, `show_company_footer`, `show_page_numbers`, `print_on_letterhead`.
- Design choices: `template_name`, `theme_color`, `font_size`.
- Text overrides: `custom_footer_message`.

## 8. Data Flow
1. **Request**: User triggers PDF generation.
2. **Services**: `OrganizationService` fetches company branding. `SampleDataService` fetches mock/real invoice data. `PrintableFrameBuilder` calculates page geometry.
3. **Context Builder**: `InvoicePreviewService` merges this into a unified dictionary.
4. **Django**: Renders the specific template in `templates/pdf/` using the context into an HTML string.
5. **WeasyPrint**: Parses the HTML string and generates a binary PDF.

## 9. Preview/Test-PDF Flow
Users can generate a "Test PDF" directly from the Invoice Design settings. This bypasses the actual invoice creation flow and uses mock data (`SampleDataService`) to immediately demonstrate how their logo, signature, letterhead, and color choices look in the final WeasyPrint output.

## 10. Organization Data Flow
The `Organization` model stores the company name, address, GSTIN, bank details, and file uploads (`logo`, `signature`, `letterhead`). The `OrganizationService` retrieves these and passes them to the template via the `company` and `org` context variables. Images are converted to absolute local `file://` paths for WeasyPrint.

## 11. Sample Data Flow
Because the user is customizing settings *before* creating a real invoice, `SampleDataService` injects realistic mock data (dummy customer, 3 items with GST, totals, notes). This guarantees the template always has data to render during the design phase.

## 12. Django Rendering Layer
Responsible for executing the conditional logic (`{% if %}` / `{% for %}`) and formatting (e.g., date formats, currency formats). It strictly separates data generation (Python) from presentation logic (HTML).

## 13. WeasyPrint Rendering Layer
WeasyPrint converts the rendered HTML string to PDF. Key behaviors:
- Respects `@page` directives for margins and background images.
- Automatically breaks long `<tbody>` sections across multiple pages.
- Repeats `<thead>` and `<tfoot>` on every new page (crucial for letterhead offset).
- Has limitations with modern CSS (e.g., complex Flexbox/Grid), requiring traditional table-based layouts for reliable multi-page rendering.

## 14. Template-Specific Geometry
Each template may define its own `@page` configuration. Standard mode uses standard margins (e.g., 15mm). Letterhead mode (`print_on_letterhead=True`) sets margins to 0, applies the physical letterhead as a full-bleed background, and uses the `body_padding_top` / `bottom` variables to push the invoice text away from the pre-printed artwork on the physical paper.

## 15. Reference vs Production Relationship
They share the same visual goal but use different technical implementations. 
- **Reference**: Clean HTML/CSS, Flexbox, relative URLs, standard web flow.
- **Production (PDF)**: Table wrappers, `file://` URLs, explicit page-break rules, header/footer spacing hacks.
Changes to the design usually require updating both files.

## 16. Current Implementation Status
Phase 1 and 2 (Foundation and Templates) are completed. 10 templates are built. The layout engine and conditional preference toggles are fully functional. PDF generation via WeasyPrint works perfectly, including multi-page letterhead spacing.

## 17. Verified Facts
- WeasyPrint requires absolute `file://` paths for images to render securely.
- Repeating a blank `<thead>` with a specific height successfully pushes content down on every page, perfectly protecting letterhead artwork.
- `page-break-inside: avoid` successfully prevents table rows and totals blocks from splitting horizontally across pages.

## 18. Known Problems
- Flexbox support in WeasyPrint is imperfect. Some templates might render slightly differently in PDF vs Reference.
- Very long unbroken text strings in item descriptions might push table boundaries off-page if not handled with `word-wrap: break-word`.
- The QR Code is currently a visual placeholder and lacks the backend generation logic.

## 19. Architectural Constraints
- **Single Source of Data**: Templates MUST NOT perform business logic or fetch data. They must only consume the unified context.
- **WeasyPrint Limitations**: Must avoid CSS Grid and complex Flexbox in the `pdf/` templates.
- **Letterhead Protection**: All PDF templates MUST wrap their content in the Master Spacer Table to guarantee letterhead offsets work on multi-page invoices.

## 20. What Must NOT Be Changed
- The data structure outputted by `InvoicePreviewService` and `SampleDataService`.
- The `PrintableFrameBuilder` layout calculation logic.
- The `<thead>` spacing hack used in PDF templates for letterhead support.

## 21. Phase C Problem Definition
(Assuming next steps): Moving from mock Sample Data to real production Invoices. Connecting the `Invoice` models to the `InvoicePreviewService`, generating real QR codes, implementing proper CGST/SGST breakdowns, and finalizing the email delivery pipeline with attached PDFs.

## 22. Recommended Investigation Method
- Run `python validate_templates.py` to check for missing context variables.
- Run `python test_matrix.py` or `python test_weasyprint.py` to generate PDFs for all templates.
- Consult `TEMPLATE_CONTENT_MAP.md` and `COMPONENT_LABORATORY.md` to understand how toggles affect layout.

## 23. Recommended Implementation Strategy
When adding a new feature (e.g., a new data field):
1. Update `SampleDataService` (for testing) and the Real Data Service.
2. Update `InvoicePreviewService` to pass it to the context.
3. Update the HTML in `templates/reference/`.
4. Update the corresponding HTML in `templates/pdf/`, ensuring it does not break WeasyPrint pagination.

## 24. Risks and Edge Cases
- **Missing Assets**: If a user deletes their logo but `show_company_logo` remains true, the template must gracefully handle the missing file (using `{% if org.logo %}`).
- **Infinite Pagination Loops**: If a single table row (`<tr>`) is taller than the entire page height, WeasyPrint will crash or hang trying to paginate it.
- **Letterhead Offset Too Large**: If the user sets a header offset that is larger than the page height, it will break rendering.

## 25. AI Handoff Instructions
**To any future AI Agent taking over this codebase:**
1. Do not modify `templates/pdf/*.html` without understanding WeasyPrint's table pagination and `@page` rules.
2. Read `TEMPLATE_CONTENT_MAP.md` and `COMPONENT_LABORATORY.md` before attempting to fix layout bugs.
3. Respect the separation between `reference/` (web preview) and `pdf/` (WeasyPrint).
4. Never introduce direct database queries inside templates. Always pass data through `InvoicePreviewService`.
5. Run `git status` and check for untracked test scripts (like `test_matrix.py`) to validate your changes locally before committing.
