"""
apps/invoices/tests/test_resolve_render_config.py

Automated test suite testing configuration resolution, adversarial/malformed input
handling, missing data fallbacks, and rendering resilience.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.invoices.services.invoice_preview_service import (
    InvoicePreviewService,
    _GLOBAL_DEFAULTS,
)
from apps.invoices.services.bill_serializer import serialize_bill_for_render
from apps.common.services.layout_engine import PrintableFrameBuilder
from apps.settings_app.models import BillTemplate, UserBillPreference, DocumentPreference

User = get_user_model()


class ResolveRenderConfigTestCase(TestCase):
    """
    Unit tests for 5-layer config merge, adversarial input handling, and fallback behavior.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="configtester",
            email="configtester@example.com",
            password="testpassword123",
        )
        self.template = BillTemplate.objects.create(
            slug="test_template",
            name="Test Template",
            template_file_path="pdf/compact_template.html",
            default_config={
                "paper_size": "A4",
                "orientation": "Portrait",
                "show_qr_code": True,
                "show_bank_details": True,
                "custom_footer_message": "Default Footer",
                "has_qr": True,
                "has_bank_details": True,
            },
        )

    def test_unknown_keys_stripped(self):
        """1. Unexpected/unknown keys in request-level overrides are stripped."""
        overrides = {
            "not_a_real_toggle": True,
            "malicious_key": "DROP TABLE",
            "show_qr_code": False,
        }
        resolved = InvoicePreviewService.resolve_render_config(
            template_slug="test_template",
            user=self.user,
            request_overrides=overrides,
        )
        self.assertNotIn("not_a_real_toggle", resolved)
        self.assertNotIn("malicious_key", resolved)
        self.assertFalse(resolved["show_qr_code"])

    def test_invalid_value_type_coercion(self):
        """2. String boolean values ('yes', 'true', '1', 'no') are safely coerced."""
        # String 'yes' -> True
        resolved = InvoicePreviewService.resolve_render_config(
            template_slug="test_template",
            user=self.user,
            request_overrides={"show_qr_code": "yes"},
        )
        self.assertIs(resolved["show_qr_code"], True)

        # String 'no' / '0' / 'false' -> False
        resolved = InvoicePreviewService.resolve_render_config(
            template_slug="test_template",
            user=self.user,
            request_overrides={"show_qr_code": "false"},
        )
        self.assertIs(resolved["show_qr_code"], False)

        # Numeric string for integer/float
        resolved = InvoicePreviewService.resolve_render_config(
            template_slug="test_template",
            user=self.user,
            request_overrides={"custom_footer_message": 12345},
        )
        self.assertEqual(resolved["custom_footer_message"], "12345")

    def test_empty_overrides_at_all_layers(self):
        """3. Empty/None overrides at all 5 layers fall back gracefully."""
        # user=None, request_overrides=None, no DocumentPreference, no UserBillPreference
        resolved = InvoicePreviewService.resolve_render_config(
            template_slug="test_template",
            user=None,
            request_overrides=None,
        )
        self.assertEqual(resolved["paper_size"], "A4")
        self.assertTrue(resolved["show_qr_code"])
        self.assertEqual(resolved["custom_footer_message"], "Default Footer")

    def test_missing_or_deleted_bill_template_slug(self):
        """4. Unknown/deleted BillTemplate slug falls back to _GLOBAL_DEFAULTS without crashing."""
        resolved = InvoicePreviewService.resolve_render_config(
            template_slug="non_existent_slug_xyz",
            user=self.user,
            request_overrides={"show_company_logo": False},
        )
        self.assertEqual(resolved["paper_size"], _GLOBAL_DEFAULTS["paper_size"])
        self.assertFalse(resolved["show_company_logo"])

    def test_user_bill_preference_layer_override(self):
        """Test layer 4: UserBillPreference overrides BillTemplate defaults."""
        UserBillPreference.objects.create(
            user=self.user,
            template=self.template,
            pref_overrides={"show_bank_details": False},
        )
        resolved = InvoicePreviewService.resolve_render_config(
            template_slug="test_template",
            user=self.user,
        )
        self.assertFalse(resolved["show_bank_details"])

    def test_serializer_missing_and_null_data(self):
        """5. Serializer handles empty/null invoice, customer, items, and company without throwing."""
        serialized = serialize_bill_for_render(
            invoice=None,
            customer=None,
            items=None,
            company=None,
            org=None,
        )
        self.assertIn("bill", serialized)
        self.assertIn("company", serialized)
        self.assertIn("customer", serialized)
        self.assertIn("items", serialized)
        self.assertIn("gst_summary", serialized)

        self.assertEqual(serialized["bill"]["number"], "")
        self.assertEqual(serialized["bill"]["subtotal"], 0.0)
        self.assertEqual(serialized["items"], [])
        self.assertEqual(serialized["gst_summary"], [])

    def test_render_pdf_with_empty_data_does_not_crash(self):
        """6. Full PDF rendering with empty/null data succeeds and returns valid PDF bytes."""
        serialized = serialize_bill_for_render(
            invoice={},
            customer={},
            items=[],
            company={},
            org=None,
        )
        config = InvoicePreviewService.resolve_render_config("test_template", None)
        layout_frame = PrintableFrameBuilder.build_frame(None, config)

        for slug in [
            "letterhead_invoice",
            "simple_invoice",
        ]:
            with self.subTest(template=slug):
                pdf_bytes = InvoicePreviewService.render_bill_pdf(
                    bill_data=serialized,
                    config=config,
                    template_file_path=f"pdf/{slug}.html",
                    layout_frame=layout_frame,
                )
                self.assertTrue(pdf_bytes.startswith(b"%PDF"))
                self.assertGreater(len(pdf_bytes), 1000)

    def test_download_invoice_with_letterhead(self):
        """7. Test PDF generation with letterhead enabled (print_on_letterhead=True)."""
        config = InvoicePreviewService.resolve_render_config(
            template_slug="letterhead_invoice",
            user=self.user,
            request_overrides={"print_on_letterhead": True},
        )
        self.assertTrue(config["print_on_letterhead"])

        serialized = serialize_bill_for_render({}, {}, [], {}, None)
        layout_frame = PrintableFrameBuilder.build_frame(None, config)

        pdf_bytes = InvoicePreviewService.render_bill_pdf(
            bill_data=serialized,
            config=config,
            template_file_path="pdf/letterhead_invoice.html",
            layout_frame=layout_frame,
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_download_invoice_without_letterhead(self):
        """8. Test PDF generation with letterhead disabled (print_on_letterhead=False)."""
        config = InvoicePreviewService.resolve_render_config(
            template_slug="letterhead_invoice",
            user=self.user,
            request_overrides={"print_on_letterhead": False},
        )
        self.assertFalse(config["print_on_letterhead"])

        serialized = serialize_bill_for_render({}, {}, [], {}, None)
        layout_frame = PrintableFrameBuilder.build_frame(None, config)

        pdf_bytes = InvoicePreviewService.render_bill_pdf(
            bill_data=serialized,
            config=config,
            template_file_path="pdf/letterhead_invoice.html",
            layout_frame=layout_frame,
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_letterhead_fallback_template(self):
        """9. Test that non-existent/invalid template slugs automatically fall back to simple_invoice."""
        for invalid_slug in ["non_existent_template", "gst_classic", "corrupted_slug"]:
            config = InvoicePreviewService.resolve_render_config(
                template_slug=invalid_slug,
                user=self.user,
                request_overrides={"print_on_letterhead": True},
            )
            serialized = serialize_bill_for_render({}, {}, [], {}, None)
            layout_frame = PrintableFrameBuilder.build_frame(None, config)

            pdf_bytes = InvoicePreviewService.render_bill_pdf(
                bill_data=serialized,
                config=config,
                template_file_path=f"pdf/{invalid_slug}.html",
                layout_frame=layout_frame,
            )
            self.assertTrue(pdf_bytes.startswith(b"%PDF"))
            self.assertGreater(len(pdf_bytes), 1000)

    def test_missing_letterhead_image(self):
        """10. Test letterhead mode when org is None or letterhead image is missing."""
        config = InvoicePreviewService.resolve_render_config(
            template_slug="simple_invoice",
            user=self.user,
            request_overrides={"print_on_letterhead": True},
        )
        serialized = serialize_bill_for_render({}, {}, [], {}, None)
        layout_frame = PrintableFrameBuilder.build_frame(None, config)

        pdf_bytes = InvoicePreviewService.render_bill_pdf(
            bill_data=serialized,
            config=config,
            template_file_path="pdf/simple_invoice.html",
            layout_frame=layout_frame,
            org=None,
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_missing_optional_company_data(self):
        """11. Test rendering when optional company/org data fields are None or missing."""
        company = {
            "name": "Minimal Company",
            "address": None,
            "city": None,
            "state": None,
            "gstin": None,
            "email": None,
            "phone": None,
            "logo_url": None,
            "signature_url": None,
            "bank_name": None,
            "acc_no": None,
            "ifsc": None,
        }
        serialized = serialize_bill_for_render(
            invoice={"number": "INV-100", "subtotal": 1000, "grand_total": 1000},
            customer={"name": "Test Customer"},
            items=[{"name": "Item 1", "quantity": 1, "rate": 1000, "amount": 1000}],
            company=company,
            org=None,
        )
        config = InvoicePreviewService.resolve_render_config(
            template_slug="simple_invoice",
            user=self.user,
            request_overrides={"print_on_letterhead": True},
        )
        layout_frame = PrintableFrameBuilder.build_frame(None, config)

        pdf_bytes = InvoicePreviewService.render_bill_pdf(
            bill_data=serialized,
            config=config,
            template_file_path="pdf/simple_invoice.html",
            layout_frame=layout_frame,
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_professional_template_preserves_path_when_letterhead_enabled(self):
        """12. Test that rendering professional_template with print_on_letterhead=True preserves template path."""
        config = InvoicePreviewService.resolve_render_config(
            template_slug="professional_template",
            user=self.user,
            request_overrides={"print_on_letterhead": True},
        )
        serialized = serialize_bill_for_render({}, {}, [], {}, None)
        layout_frame = PrintableFrameBuilder.build_frame(None, config)

        pdf_bytes = InvoicePreviewService.render_bill_pdf(
            bill_data=serialized,
            config=config,
            template_file_path="pdf/professional_template.html",
            layout_frame=layout_frame,
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_organization_letterhead_preview_view_success(self):
        """13. Test that OrganizationLetterheadPreviewView returns 200 OK without NameError."""
        from django.test import RequestFactory
        from apps.organization.views import OrganizationLetterheadPreviewView

        rf = RequestFactory()
        request = rf.get("/organization/letterhead-preview/?header=30&footer=25")
        request.user = self.user

        view = OrganizationLetterheadPreviewView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

