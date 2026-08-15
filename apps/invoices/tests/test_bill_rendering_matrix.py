"""
apps/invoices/tests/test_bill_rendering_matrix.py

Automated test suite verifying the preference toggle matrix across all 8
hand-designed invoice templates.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from apps.settings_app.models import BillTemplate

User = get_user_model()


class BillRenderingMatrixTestCase(TestCase):
    """
    Tests that elements properly show/hide across all 8 templates
    for every preference toggle.
    """

    TEMPLATES = [
        "compact_template",
        "genz",
        "landscape_template",
        "modern_template",
        "mrp_discount_template",
        "professional_template",
        "service_template",
        "vintage",
        "ledger_classic",
        "minimal_mono",
        "bold_header",
        "elegant_serif",
        "tech_grid",
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
        "show_payment_info",
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
        return render_to_string(f"pdf/{template_slug}.html", context)

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
                self.assertNotIn('<img class="logo"', html)
                self.assertNotIn('class="logo-mark"', html)

    def test_bank_off(self):
        """Test 3: When bank details are OFF, no bank details section renders."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_bank_details"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("IFSC:", html)
                self.assertNotIn("Account No:", html)
                self.assertNotIn("Bank Details:", html)

    def test_qr_off(self):
        """Test 4: When QR is OFF, no QR image renders."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_qr_code"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn('class="qr-image"', html)
                if 'class="qr"' in html:
                    after_qr = html.split('class="qr"')[1][:150]
                    self.assertNotIn("<img", after_qr)

    def test_signature_off(self):
        """Test 5: When signature is OFF, no authorized signatory line renders."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_signature"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("Authorized Signatory", html)
                self.assertNotIn("Authorised Signatory", html)
                self.assertNotIn('class="signature-image"', html)

    def test_hsn_sac_off(self):
        """Test 6: When HSN/SAC is OFF, no HSN column header renders."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_hsn_sac"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn(">HSN/SAC<", html)
                self.assertNotIn(">HSN<", html)

    def test_gst_summary_off(self):
        """Test 7: When GST summary is OFF, tax breakdown rows are suppressed."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_gst_summary"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("Central Tax", html)
                self.assertNotIn("State/UT Tax", html)

    def test_terms_off(self):
        """Test 8: When terms are OFF, terms section is suppressed."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_terms"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("Terms and Conditions:", html)

    def test_payment_info_off(self):
        """Test 9: When payment info is OFF, amount paid is suppressed."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_payment_info"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("Amount Paid", html)

    def test_company_footer_off(self):
        """Test 10: When company footer is OFF, footer message is suppressed."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_company_footer"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("digitally signed document", html)

    def test_page_numbers_off(self):
        """Test 11: When page numbers are OFF, page numbers are suppressed."""
        prefs = {p: True for p in self.PREFERENCES}
        prefs["show_page_numbers"] = False
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, prefs)
                self.assertNotIn("Page 1 / 1", html)
                self.assertNotIn("Page 1/1", html)

    def test_multiple_off_simultaneously(self):
        """Test 13: All optional toggles disabled simultaneously."""
        all_off = {p: False for p in self.PREFERENCES}
        for slug in self.TEMPLATES:
            with self.subTest(template=slug):
                html = self._render_template(slug, all_off)
                self.assertGreater(len(html), 100)
                self.assertNotIn("Bank Details:", html)
                self.assertNotIn("Authorized Signatory", html)
                self.assertNotIn("Terms and Conditions:", html)
