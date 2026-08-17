"""
apps/invoices/tests/test_bill_rendering_matrix.py

Automated test suite verifying the preference toggle matrix across the official
production templates: Professional, Compact, and Vintage.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from apps.settings_app.models import BillTemplate
try:
    import weasyprint
except ImportError:
    weasyprint = None

User = get_user_model()


class BillRenderingMatrixTestCase(TestCase):
    """
    Tests that elements properly show/hide across the three official templates
    for every preference toggle.
    """

    TEMPLATES = [
        "professional_template",
        "compact_template",
        "vintage",
    ]

    PREFERENCES = [
        "show_company_logo",
        "show_company_header",
        "show_company_footer",
        "show_qr_code",
        "show_bank_details",
        "show_gst_summary",
        "show_hsn_sac",
        "show_signature",
        "show_terms",
        "show_page_numbers",
        "show_print_date",
        "print_on_letterhead",
    ]

    def setUp(self):
        self.user = User.objects.create_user(
            username="testmatrixuser",
            email="testmatrix@example.com",
            password="testpassword123",
            first_name="Matrix",
            last_name="Tester",
        )
        # Ensure BillTemplate rows exist
        from django.core.management import call_command
        call_command("seed_bill_templates", verbosity=0)

    def _render_template(self, template_slug: str, prefs: dict) -> str:
        custom_prefs = prefs.copy()
        custom_prefs["template_name"] = template_slug
        context = InvoicePreviewService.get_preview_context(
            self.user,
            custom_prefs=custom_prefs,
            preview_mode="demo",
        )
        resolved_path = InvoicePreviewService.resolve_template_path(template_slug)
        return render_to_string(resolved_path, context)

    def test_everything_on(self):
        """Test 1: All preferences enabled renders without error."""
        all_on = {p: True for p in self.PREFERENCES}
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, all_on)
                self.assertGreater(len(html), 100, f"Template {slug} produced empty output")

    def test_logo_off(self):
        """Test 2: When logo is OFF, no logo image or logo-mark renders."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_company_logo"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn('<img class="company-logo"', html)

    def test_bank_off(self):
        """Test 3: When bank details are OFF, no bank details section renders."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_bank_details"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("IFSC Code:", html)
                self.assertNotIn("Bank Name:", html)
                self.assertNotIn("Account No:", html)

    def test_qr_off(self):
        """Test 4: When QR is OFF, no QR image or fake QR placeholder renders."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_qr_code"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn('class="qr-img"', html)
                self.assertNotIn('class="qr"', html)
                self.assertNotIn('class="qr-box"', html)

    def test_signature_modes_and_disclaimer_matrix(self):
        """Test 5: Verify signature modes (none, image, authorized_signatory) x disclaimer (OFF, ON)."""
        prefs = {p: True for p in self.PREFERENCES}

        for mode in ["none", "image", "authorized_signatory"]:
            for disclaimer in [False, True]:
                for slug in self.TEMPLATES:
                    with self.subTest(template=slug, mode=mode, disclaimer=disclaimer):
                        custom_prefs = prefs.copy()
                        custom_prefs["template_name"] = slug
                        context = InvoicePreviewService.get_preview_context(
                            self.user,
                            custom_prefs=custom_prefs,
                            preview_mode="demo",
                        )
                        context["company"]["signature_mode"] = mode
                        context["company"]["authorized_signatory_name"] = "Authorized Signatory"
                        context["company"]["show_computer_generated_disclaimer"] = disclaimer

                        resolved_path = InvoicePreviewService.resolve_template_path(slug)
                        html = render_to_string(resolved_path, context)

                        if disclaimer:
                            self.assertIn("computer-generated invoice", html)
                        else:
                            self.assertNotIn("computer-generated invoice", html)

                        if mode == "none":
                            self.assertNotIn('class="signature-img"', html)
                        elif mode == "authorized_signatory":
                            self.assertIn("Authorized Signatory", html)

    def test_hsn_sac_off(self):
        """Test 6: When HSN/SAC is OFF, no HSN column header or badge renders."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_hsn_sac"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("HSN/SAC:", html)

    def test_gst_summary_off(self):
        """Test 7: When GST summary is OFF, tax breakdown table is suppressed."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_gst_summary"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("CGST Rate", html)
                self.assertNotIn("SGST Rate", html)

    def test_terms_off(self):
        """Test 8: When terms are OFF, terms section is suppressed."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_terms"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("Terms &amp; Conditions:", html)

    def test_payment_info_is_not_rendered(self):
        """Test 9: Verify payment info (Amount Paid) is never rendered on invoices."""
        prefs = {p: True for p in self.PREFERENCES}
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("Amount Paid", html)
                self.assertNotIn("Balance Due", html)

    def test_multiple_off_simultaneously(self):
        """Test 10: All optional toggles disabled simultaneously."""
        all_off = {p: False for p in self.PREFERENCES}
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, all_off)
                self.assertGreater(len(html), 100)
                self.assertNotIn("Bank Name:", html)
                self.assertNotIn("Authorized Signatory", html)
                self.assertNotIn("Terms &amp; Conditions:", html)

    def test_multipage_pdf_generation(self):
        """Test 11: Verify 50+ line items generate valid PDF bytes without rendering errors."""
        if not weasyprint:
            return

        prefs = {p: True for p in self.PREFERENCES}
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                custom_prefs = prefs.copy()
                custom_prefs["template_name"] = slug
                context = InvoicePreviewService.get_preview_context(
                    self.user,
                    custom_prefs=custom_prefs,
                    preview_mode="demo",
                )

                # Create 50 line items to force multi-page rendering
                items = []
                for i in range(1, 51):
                    items.append({
                        "index": i,
                        "name": f"Product Item #{i} with extra description details for multi-page stress testing",
                        "hsn": "84713010",
                        "quantity": i,
                        "unit": "Pcs",
                        "rate": "100.00",
                        "tax_pct": "18.00",
                        "tax_amount": "18.00",
                        "amount": f"{i * 100}.00",
                        "description": "Comprehensive specification text line for multi-page layout verification.",
                    })
                context["items"] = items

                resolved_path = InvoicePreviewService.resolve_template_path(slug)
                html_str = render_to_string(resolved_path, context)
                pdf_bytes = weasyprint.HTML(string=html_str, base_url="file://").write_pdf()

                self.assertIsInstance(pdf_bytes, bytes)
                self.assertTrue(pdf_bytes.startswith(b"%PDF"))
                self.assertGreater(len(pdf_bytes), 5000, "Multi-page PDF should generate substantial valid binary data")
