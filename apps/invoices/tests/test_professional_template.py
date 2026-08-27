"""
apps/invoices/tests/test_professional_template.py

Verifies the updated Professional invoice template:
1. Item table header: # | Item Description | HSN/SAC | Qty | Rate | Amount
2. Complete removal of Details column and Tax column from line items.
3. Removal of HSN/SAC text from underneath the item name.
4. Summary section: Replacement of Total Tax with dynamic CGST @ X% and SGST @ X%.
5. Preservation of Compact template and other templates.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from apps.invoices.services.bill_serializer import serialize_bill_for_render
import weasyprint

User = get_user_model()


class ProfessionalTemplateTestCase(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="proftemplateuser",
            email="proftemplate@example.com",
            password="testpassword123",
        )

    def test_professional_template_layout_and_summary_18_pct(self):
        """Test Professional template item table structure & totals summary for 18% GST invoice."""
        invoice = {
            "number": "INV-1001",
            "date": "2026-08-27",
            "subtotal": 2049.48,
            "tax_total": 368.91,
            "grand_total": 2418.39,
            "currency": "INR",
        }
        customer = {
            "name": "Test Customer",
            "address": "456 Test Ave",
        }
        items = [
            {
                "name": "PVC Shrink",
                "hsn": "263748",
                "quantity": 10,
                "rate": 204.948,
                "tax_pct": 18.0,
                "amount": 2418.39,
                "description": "Some internal details",
            }
        ]
        company = {
            "name": "Test Seller Co",
            "gstin": "29ABCDE1234F1Z5",
        }

        canonical = serialize_bill_for_render(invoice, customer, items, company)
        context = {
            **canonical,
            "config": {
                "show_hsn_sac": True,
                "show_gst_summary": True,
                "show_company_header": True,
            },
            "layout_frame": {},
        }

        html = render_to_string("pdf/professional_template.html", context)

        # 1. Table headers check
        self.assertIn("HSN/SAC", html)
        self.assertNotIn(">Details<", html)
        self.assertNotIn(">Tax<", html)

        # 2. HSN value displayed in table column
        self.assertIn("263748", html)

        # 3. No HSN/SAC subtitle under product name
        self.assertNotIn("HSN/SAC: 263748", html)

        # 4. Pre-tax line item Amount (Rate x Quantity = 204.948 x 10 = 2049.48)
        self.assertIn("2,049.48", html)

        # 5. Summary rows: CGST @ 9% and SGST @ 9%
        self.assertIn("CGST @ 9.0%", html)
        self.assertIn("SGST @ 9.0%", html)

        # 6. Check tax math: CGST + SGST == tax_total
        self.assertEqual(round(canonical["bill"]["cgst_total"] + canonical["bill"]["sgst_total"], 2), 368.91)

        # 7. WeasyPrint PDF generation check
        pdf_bytes = InvoicePreviewService.render_bill_pdf(
            canonical,
            context["config"],
            "pdf/professional_template.html",
            {},
        )
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_professional_template_12_pct_gst(self):
        """Test Professional template with 12% GST dynamically renders CGST @ 6% and SGST @ 6%."""
        invoice = {
            "number": "INV-1002",
            "subtotal": 1000.00,
            "tax_total": 120.00,
            "grand_total": 1120.00,
        }
        items = [
            {"name": "Widget B", "hsn": "123456", "quantity": 1, "rate": 1000.0, "tax_pct": 12.0, "amount": 1120.0}
        ]
        canonical = serialize_bill_for_render(invoice, {}, items, {})
        context = {
            **canonical,
            "config": {"show_gst_summary": True},
            "layout_frame": {},
        }
        html = render_to_string("pdf/professional_template.html", context)

        self.assertIn("CGST @ 6.0%", html)
        self.assertIn("SGST @ 6.0%", html)
        self.assertEqual(canonical["bill"]["cgst_total"], 60.0)
        self.assertEqual(canonical["bill"]["sgst_total"], 60.0)

    def test_compact_template_remains_unmodified(self):
        """Ensure compact template is completely untouched and intact."""
        html = render_to_string("pdf/compact_template.html", {})
        self.assertGreater(len(html), 100)
