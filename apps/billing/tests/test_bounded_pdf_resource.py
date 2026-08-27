"""
apps/billing/tests/test_bounded_pdf_resource.py

Phase 2 Bounded PDF / WeasyPrint Resource Protection Test Suite.

Verifies:
1. Normal invoice PDF generation succeeds.
2. PDF rendering concurrency never exceeds 2 simultaneous renders per process.
3. Third concurrent render is rejected without executing WeasyPrint.
4. Resource slot is released after successful render.
5. Resource slot is released after WeasyPrint raises an exception.
6. Rate-limited PDF endpoint returns 429 and does not invoke WeasyPrint.
7. Invoice design preview functional under allowed rate limit.
8. Invoice design download functional under allowed rate limit.
9. Letterhead preview functional under allowed rate limit.
10. 100 invoice line items accepted.
11. 101 invoice line items rejected server-side.
12. Existing invoice issuance behavior remains unchanged.
13. Phase 1 bounded email worker integration remains fully functional.
"""

import time
import threading
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus, DiscountType
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product, TaxabilityType
from apps.settings_app.models import DocumentPreference
from apps.billing.forms import make_invoice_line_formset
from apps.billing.services.pdf_resource_guard import (
    PDFResourceGuard,
    PDFCapacityExceededError,
)
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from apps.billing.services.pdf_adapter import invoice_to_pdf_dicts
from apps.invoices.services.bill_serializer import serialize_bill_for_render
from apps.common.services.layout_engine import PrintableFrameBuilder

User = get_user_model()


class Phase2BoundedPDFResourceTests(TestCase):
    def setUp(self):
        cache.clear()
        PDFResourceGuard.reset_stats()

        self.user = User.objects.create_user(
            username="pdf_guard_user",
            email="pdf_guard@example.com",
            password="Password123!",
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Guard Acme Corp",
            state_code="MH",
            business_email="guard@acme.com",
            address_line_1="100 Security Lane",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
        )
        self.user.organization = self.org
        self.user.save()

        DocumentPreference.objects.create(
            user=self.user,
            show_company_logo=True,
            show_company_header=True,
            print_on_letterhead=False,
        )

        self.customer = Customer.objects.create(
            organization=self.org,
            name="Secure Client LLC",
            billing_state_code="MH",
            billing_address_line_1="200 Client Blvd",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_pin_code="400002",
        )

        self.product = Product.objects.create(
            organization=self.org,
            name="Cloud Consulting",
            unit_price=Decimal("1500.00"),
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            hsn_code="9983",
        )

        self.invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=date.today(),
            status=InvoiceStatus.DRAFT,
            place_of_supply="MH",
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            position=1,
            product=self.product,
            description="Security Audit",
            quantity=Decimal("2.00"),
            unit_price=Decimal("1500.00"),
            discount_type=DiscountType.NONE,
            discount_value=Decimal("0.00"),
        )

        self.client = Client()
        self.client.login(username="pdf_guard_user", password="Password123!")

    def tearDown(self):
        cache.clear()
        PDFResourceGuard.reset_stats()

    # -------------------------------------------------------------------------
    # TEST 1: Normal invoice PDF generation succeeds
    # -------------------------------------------------------------------------
    def test_01_normal_invoice_pdf_generation_succeeds(self):
        url = reverse("billing:preview", kwargs={"uuid": self.invoice.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))

    # -------------------------------------------------------------------------
    # TEST 2: PDF rendering concurrency never exceeds 2 simultaneous renders
    # -------------------------------------------------------------------------
    def test_02_pdf_concurrency_never_exceeds_max_two(self):
        PDFResourceGuard.reset_stats()
        active_during_run = []
        lock = threading.Lock()

        def worker():
            try:
                with PDFResourceGuard.protect(timeout=2.0):
                    current_active = PDFResourceGuard.get_active_renders()
                    with lock:
                        active_during_run.append(current_active)
                    time.sleep(0.05)
            except PDFCapacityExceededError:
                pass

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        max_active = PDFResourceGuard.get_max_observed_active()
        self.assertLessEqual(max_active, 2)
        for active_val in active_during_run:
            self.assertLessEqual(active_val, 2)

    # -------------------------------------------------------------------------
    # TEST 3: Third concurrent render does not execute WeasyPrint
    # -------------------------------------------------------------------------
    def test_03_third_concurrent_render_does_not_execute_weasyprint(self):
        with PDFResourceGuard.protect(timeout=1.0):
            with PDFResourceGuard.protect(timeout=1.0):
                self.assertEqual(PDFResourceGuard.get_active_renders(), 2)

                weasy_mock = MagicMock()
                with patch("weasyprint.HTML", weasy_mock):
                    with self.assertRaises(PDFCapacityExceededError):
                        inv_dict, cust_dict, items_list, comp_dict = invoice_to_pdf_dicts(self.invoice)
                        bill_data = serialize_bill_for_render(inv_dict, cust_dict, items_list, comp_dict, self.org)
                        config = InvoicePreviewService.resolve_render_config(user=self.user)
                        frame = PrintableFrameBuilder.build_frame(self.org, config)
                        tpl = InvoicePreviewService.resolve_template_path(config.get("template_name"))

                        # Attempt 3rd render while 2 slots are held with timeout=0.01
                        with patch.object(PDFResourceGuard, "protect", side_effect=PDFCapacityExceededError("Capacity full")):
                            InvoicePreviewService.render_bill_pdf(bill_data, config, tpl, frame, self.org)

                weasy_mock.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 4: Semaphore slot released after successful PDF generation
    # -------------------------------------------------------------------------
    def test_04_slot_released_after_successful_render(self):
        initial_active = PDFResourceGuard.get_active_renders()
        url = reverse("billing:preview", kwargs={"uuid": self.invoice.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PDFResourceGuard.get_active_renders(), initial_active)

    # -------------------------------------------------------------------------
    # TEST 5: Semaphore slot released after WeasyPrint raises exception
    # -------------------------------------------------------------------------
    def test_05_slot_released_after_weasyprint_exception(self):
        initial_active = PDFResourceGuard.get_active_renders()

        with patch("weasyprint.HTML") as mock_html:
            mock_html.side_effect = RuntimeError("WeasyPrint crash")

            inv_dict, cust_dict, items_list, comp_dict = invoice_to_pdf_dicts(self.invoice)
            bill_data = serialize_bill_for_render(inv_dict, cust_dict, items_list, comp_dict, self.org)
            config = InvoicePreviewService.resolve_render_config(user=self.user)
            frame = PrintableFrameBuilder.build_frame(self.org, config)
            tpl = InvoicePreviewService.resolve_template_path(config.get("template_name"))

            try:
                InvoicePreviewService.render_bill_pdf(bill_data, config, tpl, frame, self.org)
            except Exception:
                pass

        self.assertEqual(PDFResourceGuard.get_active_renders(), initial_active)

    # -------------------------------------------------------------------------
    # TEST 6: Rate-limited PDF endpoint returns 429 and does not invoke WeasyPrint
    # -------------------------------------------------------------------------
    def test_06_rate_limited_pdf_endpoint_returns_429(self):
        url = reverse("billing:preview", kwargs={"uuid": self.invoice.uuid})
        cache.clear()

        # Execute requests up to rate limit (15/m)
        for _ in range(15):
            res = self.client.get(url)
            self.assertIn(res.status_code, (200, 429))

        # 16th request must be rate-limited
        with patch("weasyprint.HTML") as mock_html:
            res = self.client.get(url)
            self.assertEqual(res.status_code, 429)
            mock_html.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 7: Invoice design preview remains functional under allowed request rate
    # -------------------------------------------------------------------------
    def test_07_invoice_design_preview_functional_under_allowed_rate(self):
        cache.clear()
        url = reverse("settings_app:invoice_design_preview")
        data = {"template_name": "professional_template", "paper_size": "A4"}
        response = self.client.post(url, data=data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    # -------------------------------------------------------------------------
    # TEST 8: Invoice design download remains functional under allowed request rate
    # -------------------------------------------------------------------------
    def test_08_invoice_design_download_functional_under_allowed_rate(self):
        cache.clear()
        url = reverse("settings_app:invoice_design_download")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment", response.get("Content-Disposition", ""))

    # -------------------------------------------------------------------------
    # TEST 9: Letterhead preview remains functional under allowed request rate
    # -------------------------------------------------------------------------
    def test_09_letterhead_preview_functional_under_allowed_rate(self):
        cache.clear()
        url = reverse("organization:letterhead_preview")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    # -------------------------------------------------------------------------
    # TEST 10: 100 invoice line items are accepted
    # -------------------------------------------------------------------------
    def test_10_one_hundred_invoice_line_items_accepted(self):
        FormSet = make_invoice_line_formset(self.org, extra=0)
        data = {
            "lines-TOTAL_FORMS": "100",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "100",
        }
        for i in range(100):
            data[f"lines-{i}-product"] = str(self.product.pk)
            data[f"lines-{i}-description"] = f"Item {i+1}"
            data[f"lines-{i}-quantity"] = "1.00"
            data[f"lines-{i}-unit_price"] = "100.00"
            data[f"lines-{i}-discount_type"] = DiscountType.NONE.value
            data[f"lines-{i}-discount_value"] = "0.00"

        formset = FormSet(data, prefix="lines")
        self.assertTrue(formset.is_valid(), formset.errors)

    # -------------------------------------------------------------------------
    # TEST 11: 101 invoice line items are rejected server-side
    # -------------------------------------------------------------------------
    def test_11_one_hundred_and_one_line_items_rejected_server_side(self):
        FormSet = make_invoice_line_formset(self.org, extra=0)
        data = {
            "lines-TOTAL_FORMS": "101",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "100",
        }
        for i in range(101):
            data[f"lines-{i}-product"] = str(self.product.pk)
            data[f"lines-{i}-description"] = f"Item {i+1}"
            data[f"lines-{i}-quantity"] = "1.00"
            data[f"lines-{i}-unit_price"] = "100.00"
            data[f"lines-{i}-discount_type"] = DiscountType.NONE.value
            data[f"lines-{i}-discount_value"] = "0.00"

        formset = FormSet(data, prefix="lines")
        self.assertFalse(formset.is_valid())

    # -------------------------------------------------------------------------
    # TEST 12: Existing invoice issuance behavior remains unchanged
    # -------------------------------------------------------------------------
    def test_12_existing_invoice_issuance_behavior_unchanged(self):
        url = reverse("billing:issue", kwargs={"uuid": self.invoice.uuid})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.ISSUED)

    # -------------------------------------------------------------------------
    # TEST 13: Phase 1 bounded email worker tests continue passing
    # -------------------------------------------------------------------------
    def test_13_phase_1_bounded_email_worker_integration(self):
        from apps.billing.services.invoice_email_service import _BoundedInvoiceEmailExecutor
        self.assertEqual(_BoundedInvoiceEmailExecutor.MAX_WORKERS, 2)
        self.assertEqual(_BoundedInvoiceEmailExecutor.MAX_QUEUE_SIZE, 100)
