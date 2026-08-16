"""
apps/billing/tests/test_security.py — Phase 11 Security & Historical Integrity Tests

Covers all 25 minimum required security points + defense-in-depth:
1. Cross-org Invoice detail denied (404).
2. Cross-org Invoice edit denied (404).
3. Cross-org Invoice delete denied (404).
4. Cross-org Invoice issue denied (404).
5. Cross-org Invoice cancel denied (404).
6. Cross-org Invoice PDF denied (404).
7. Cross-org Customer selection denied in Form and Backend.
8. Cross-org Product selection denied in Form and Backend.
9. Anonymous Invoice access denied (redirects to login).
10. Anonymous PDF access denied (redirects to login).
11. Issued Invoice edit denied (UI and backend).
12. Issued Invoice delete denied (UI and backend).
13. Issued Invoice reissue denied.
14. Cancelled Invoice edit denied.
15. Cancelled Invoice delete denied.
16. Cancelled Invoice reissue denied.
17. Customer changes do not affect historical Invoice snapshots.
18. Product changes do not affect historical InvoiceLine snapshots.
19. Customer deletion preserves Invoice (SET_NULL) with snapshots intact.
20. Product deletion preserves InvoiceLine (SET_NULL) with snapshots intact.
21. Tampered Invoice number cannot override lifecycle numbering.
22. Tampered totals cannot override backend calculations.
23. Tampered snapshot fields cannot rewrite historical data.
24. Destructive GET methods are rejected (HTTP 405).
25. CSRF protection remains active.
26. Cross-org Customer JSON search & detail APIs denied/filtered.
27. Cross-org Product JSON search API filtered.
28. Cross-org Draft calculation preview denied.
29. Direct backend finalize_invoice / prepare_invoice_snapshots cross-org rejection.
"""

import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse

from apps.billing.forms import InvoiceForm, make_invoice_line_formset
from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus, DiscountType
from apps.billing.services.calculation_engine import finalize_invoice, validate_invoice
from apps.billing.services.lifecycle import (
    issue_invoice,
    cancel_invoice,
    delete_invoice,
    prepare_invoice_snapshots,
)
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product, TaxabilityType, PriceBasis
from apps.settings_app.models import InvoicePreference, DocumentPreference

User = get_user_model()


class Phase11SecurityTests(TestCase):
    def setUp(self):
        # Organization A setup
        self.user_a = User.objects.create_user(
            username="user_a",
            email="user_a@example.com",
            password="password123",
            first_name="User",
            last_name="A"
        )
        self.org_a = Organization.objects.create(
            owner=self.user_a,
            business_name="Org Alpha",
            business_email="alpha@example.com",
            state_code="27",
            address_line_1="Alpha St",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            country="India"
        )
        self.user_a.organization = self.org_a
        self.user_a.save()
        self.pref_a = InvoicePreference.objects.create(
            user=self.user_a,
            invoice_prefix="ALPHA",
            starting_number=100
        )
        self.doc_pref_a = DocumentPreference.objects.create(
            user=self.user_a,
            show_company_logo=True
        )

        self.customer_a = Customer.objects.create(
            organization=self.org_a,
            name="Alpha Customer",
            billing_state_code="27",
            billing_state="Maharashtra",
            billing_city="Mumbai",
            billing_address_line_1="Alpha Cust Road",
            billing_pin_code="400001"
        )
        self.product_a = Product.objects.create(
            organization=self.org_a,
            name="Alpha Product",
            unit_price=Decimal("1000.00"),
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            price_basis=PriceBasis.EXCLUSIVE,
            hsn_code="9983"
        )

        # Organization B setup (Attacker / Other Tenant)
        self.user_b = User.objects.create_user(
            username="user_b",
            email="user_b@example.com",
            password="password123",
            first_name="User",
            last_name="B"
        )
        self.org_b = Organization.objects.create(
            owner=self.user_b,
            business_name="Org Beta",
            business_email="beta@example.com",
            state_code="29",
            address_line_1="Beta St",
            city="Bengaluru",
            state="Karnataka",
            pincode="560001",
            country="India"
        )
        self.user_b.organization = self.org_b
        self.user_b.save()
        self.pref_b = InvoicePreference.objects.create(
            user=self.user_b,
            invoice_prefix="BETA",
            starting_number=200
        )
        self.customer_b = Customer.objects.create(
            organization=self.org_b,
            name="Beta Customer",
            billing_state_code="29",
            billing_state="Karnataka",
            billing_city="Bengaluru",
            billing_address_line_1="Beta Cust Road",
            billing_pin_code="560001"
        )
        self.product_b = Product.objects.create(
            organization=self.org_b,
            name="Beta Product",
            unit_price=Decimal("2000.00"),
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            price_basis=PriceBasis.EXCLUSIVE,
            hsn_code="9984"
        )

        # Invoices for Org A
        self.draft_a = Invoice.objects.create(
            organization=self.org_a,
            customer=self.customer_a,
            status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(),
            place_of_supply="27",
            customer_name_snapshot=self.customer_a.name,
            customer_gstin_snapshot="",
            customer_billing_address_snapshot=self.customer_a.full_billing_address,
            customer_state_code_snapshot=self.customer_a.billing_state_code
        )
        self.draft_a_line = InvoiceLine.objects.create(
            invoice=self.draft_a,
            position=1,
            product=self.product_a,
            quantity=Decimal("2.000"),
            unit_price=Decimal("1000.00"),
            discount_type=DiscountType.NONE,
            discount_value=Decimal("0.00")
        )

        # Issued Invoice for Org A
        self.issued_a = Invoice.objects.create(
            organization=self.org_a,
            customer=self.customer_a,
            status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(),
            place_of_supply="27"
        )
        InvoiceLine.objects.create(
            invoice=self.issued_a,
            position=1,
            product=self.product_a,
            quantity=Decimal("1.000"),
            unit_price=Decimal("1000.00"),
            discount_type=DiscountType.NONE,
            discount_value=Decimal("0.00")
        )
        finalize_invoice(self.issued_a)
        self.issued_a.refresh_from_db()

        # Invoices for Org B
        self.draft_b = Invoice.objects.create(
            organization=self.org_b,
            customer=self.customer_b,
            status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(),
            place_of_supply="29"
        )
        InvoiceLine.objects.create(
            invoice=self.draft_b,
            position=1,
            product=self.product_b,
            quantity=Decimal("1.000"),
            unit_price=Decimal("2000.00"),
            discount_type=DiscountType.NONE,
            discount_value=Decimal("0.00")
        )

        # Clients
        self.client_a = Client()
        self.client_a.force_login(self.user_a)

        self.client_b = Client()
        self.client_b.force_login(self.user_b)

        self.anon_client = Client()

    # -----------------------------------------------------------------------
    # 1 - 6: Cross-Org Direct UUID Access (IDOR Prevention)
    # -----------------------------------------------------------------------

    def test_01_cross_org_invoice_detail_denied(self):
        """Org B cannot view Org A's invoice detail via UUID (must 404)."""
        resp = self.client_b.get(reverse("billing:detail", kwargs={"uuid": self.issued_a.uuid}))
        self.assertEqual(resp.status_code, 404)

    def test_02_cross_org_invoice_edit_denied(self):
        """Org B cannot edit Org A's invoice via UUID (must 404)."""
        resp = self.client_b.get(reverse("billing:edit", kwargs={"uuid": self.draft_a.uuid}))
        self.assertEqual(resp.status_code, 404)

        resp_post = self.client_b.post(reverse("billing:edit", kwargs={"uuid": self.draft_a.uuid}), {})
        self.assertEqual(resp_post.status_code, 404)

    def test_03_cross_org_invoice_delete_denied(self):
        """Org B cannot delete Org A's draft invoice (must 404)."""
        resp = self.client_b.get(reverse("billing:delete", kwargs={"uuid": self.draft_a.uuid}))
        self.assertEqual(resp.status_code, 404)

        resp_post = self.client_b.post(reverse("billing:delete", kwargs={"uuid": self.draft_a.uuid}))
        self.assertEqual(resp_post.status_code, 404)
        self.assertTrue(Invoice.objects.filter(uuid=self.draft_a.uuid).exists())

    def test_04_cross_org_invoice_issue_denied(self):
        """Org B cannot issue Org A's invoice (must 404)."""
        resp = self.client_b.post(reverse("billing:issue", kwargs={"uuid": self.draft_a.uuid}))
        self.assertEqual(resp.status_code, 404)
        self.draft_a.refresh_from_db()
        self.assertEqual(self.draft_a.status, InvoiceStatus.DRAFT)

    def test_05_cross_org_invoice_cancel_denied(self):
        """Org B cannot cancel Org A's issued invoice (must 404)."""
        resp = self.client_b.post(reverse("billing:cancel", kwargs={"uuid": self.issued_a.uuid}))
        self.assertEqual(resp.status_code, 404)
        self.issued_a.refresh_from_db()
        self.assertEqual(self.issued_a.status, InvoiceStatus.ISSUED)

    def test_06_cross_org_invoice_pdf_denied(self):
        """Org B cannot download/preview Org A's invoice PDF (must 404)."""
        resp = self.client_b.get(reverse("billing:preview", kwargs={"uuid": self.issued_a.uuid}))
        self.assertEqual(resp.status_code, 404)

    # -----------------------------------------------------------------------
    # 7 - 8: Cross-Org Customer / Product Selection & Form Tampering
    # -----------------------------------------------------------------------

    def test_07_cross_org_customer_selection_denied(self):
        """Org A cannot attach Org B's customer to an invoice."""
        # Form queryset scoping check
        form = InvoiceForm(organization=self.org_a)
        self.assertNotIn(self.customer_b, form.fields["customer"].queryset)

        # Form submission validation check
        post_data = {
            "customer": str(self.customer_b.id),
            "invoice_date": str(datetime.date.today()),
            "place_of_supply": "27"
        }
        form_bound = InvoiceForm(post_data, organization=self.org_a)
        self.assertFalse(form_bound.is_valid())
        self.assertIn("customer", form_bound.errors)

    def test_08_cross_org_product_selection_denied(self):
        """Org A cannot attach Org B's product to an invoice line."""
        LineFormSet = make_invoice_line_formset(self.org_a)
        formset_data = {
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product_b.id),
            "lines-0-quantity": "1.000",
            "lines-0-unit_price": "2000.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0.00",
        }
        formset = LineFormSet(formset_data)
        self.assertFalse(formset.is_valid())
        self.assertIn("product", formset.errors[0])

    # -----------------------------------------------------------------------
    # 9 - 10: Anonymous Access Denied
    # -----------------------------------------------------------------------

    def test_09_anonymous_invoice_access_denied(self):
        """Unauthenticated requests to any invoice endpoint are redirected to login."""
        urls = [
            reverse("billing:index"),
            reverse("billing:create"),
            reverse("billing:detail", kwargs={"uuid": self.issued_a.uuid}),
            reverse("billing:edit", kwargs={"uuid": self.draft_a.uuid}),
            reverse("billing:delete", kwargs={"uuid": self.draft_a.uuid}),
            reverse("billing:issue", kwargs={"uuid": self.draft_a.uuid}),
            reverse("billing:cancel", kwargs={"uuid": self.issued_a.uuid}),
            reverse("billing:api_customers"),
            reverse("billing:api_customer_detail", kwargs={"pk": self.customer_a.pk}),
            reverse("billing:api_products"),
        ]
        for url in urls:
            resp = self.anon_client.get(url)
            self.assertEqual(resp.status_code, 302, f"Failed for {url}")
            self.assertIn("/login/", resp.headers.get("Location", ""))

    def test_10_anonymous_pdf_access_denied(self):
        """Unauthenticated requests to preview/download PDF are redirected to login."""
        url = reverse("billing:preview", kwargs={"uuid": self.issued_a.uuid})
        resp = self.anon_client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login/", resp.headers.get("Location", ""))

    # -----------------------------------------------------------------------
    # 11 - 13: Issued Invoice Immutability & Reissue Denied
    # -----------------------------------------------------------------------

    def test_11_issued_invoice_edit_denied(self):
        """Issued invoice cannot be edited via GET or POST."""
        url = reverse("billing:edit", kwargs={"uuid": self.issued_a.uuid})
        resp_get = self.client_a.get(url)
        self.assertEqual(resp_get.status_code, 302)
        self.assertRedirects(resp_get, reverse("billing:detail", kwargs={"uuid": self.issued_a.uuid}))

        resp_post = self.client_a.post(url, {"notes": "Malicious edit"})
        self.assertEqual(resp_post.status_code, 302)
        self.issued_a.refresh_from_db()
        self.assertNotEqual(self.issued_a.notes, "Malicious edit")

    def test_12_issued_invoice_delete_denied(self):
        """Issued invoice cannot be deleted via view or service."""
        url = reverse("billing:delete", kwargs={"uuid": self.issued_a.uuid})
        resp = self.client_a.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Invoice.objects.filter(uuid=self.issued_a.uuid).exists())

        with self.assertRaises(ValidationError):
            delete_invoice(self.issued_a)

    def test_13_issued_invoice_reissue_denied(self):
        """Issued invoice cannot be re-issued via view or service."""
        url = reverse("billing:issue", kwargs={"uuid": self.issued_a.uuid})
        resp = self.client_a.post(url)
        self.assertEqual(resp.status_code, 302)

        with self.assertRaises(ValidationError):
            issue_invoice(self.issued_a)

        with self.assertRaises(ValidationError):
            finalize_invoice(self.issued_a)

    # -----------------------------------------------------------------------
    # 14 - 16: Cancelled Invoice Protection
    # -----------------------------------------------------------------------

    def test_14_cancelled_invoice_edit_denied(self):
        """Cancelled invoice remains accessible for viewing but cannot be edited."""
        cancel_invoice(self.issued_a)
        self.issued_a.refresh_from_db()
        self.assertEqual(self.issued_a.status, InvoiceStatus.CANCELLED)

        # View detail remains accessible
        resp_detail = self.client_a.get(reverse("billing:detail", kwargs={"uuid": self.issued_a.uuid}))
        self.assertEqual(resp_detail.status_code, 200)

        # Edit is rejected
        url_edit = reverse("billing:edit", kwargs={"uuid": self.issued_a.uuid})
        resp_edit = self.client_a.get(url_edit)
        self.assertEqual(resp_edit.status_code, 302)

    def test_15_cancelled_invoice_delete_denied(self):
        """Cancelled invoice cannot be deleted."""
        cancel_invoice(self.issued_a)
        self.issued_a.refresh_from_db()

        url = reverse("billing:delete", kwargs={"uuid": self.issued_a.uuid})
        resp = self.client_a.post(url)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Invoice.objects.filter(uuid=self.issued_a.uuid).exists())

        with self.assertRaises(ValidationError):
            delete_invoice(self.issued_a)

    def test_16_cancelled_invoice_reissue_denied(self):
        """Cancelled invoice cannot be re-issued."""
        cancel_invoice(self.issued_a)
        self.issued_a.refresh_from_db()

        with self.assertRaises(ValidationError):
            issue_invoice(self.issued_a)

        with self.assertRaises(ValidationError):
            finalize_invoice(self.issued_a)

    # -----------------------------------------------------------------------
    # 17 - 18: Historical Integrity on Master Record Changes
    # -----------------------------------------------------------------------

    def test_17_customer_changes_do_not_affect_historical_invoice(self):
        """Modifying customer master does not alter issued invoice snapshots."""
        original_name = self.issued_a.customer_name_snapshot
        original_address = self.issued_a.customer_billing_address_snapshot
        original_total = self.issued_a.grand_total

        # Mutate master Customer
        self.customer_a.name = "Renamed Corp International"
        self.customer_a.billing_address_line_1 = "999 Altered Blvd"
        self.customer_a.billing_state_code = "29"
        self.customer_a.save()

        self.issued_a.refresh_from_db()
        self.assertEqual(self.issued_a.customer_name_snapshot, original_name)
        self.assertEqual(self.issued_a.customer_billing_address_snapshot, original_address)
        self.assertEqual(self.issued_a.grand_total, original_total)

    def test_18_product_changes_do_not_affect_historical_invoice_line(self):
        """Modifying product master does not alter issued line item snapshots or calculations."""
        line = self.issued_a.lines.first()
        original_product_name = line.product_name_snapshot
        original_gst_rate = line.gst_rate_snapshot
        original_taxable = line.taxable_value
        original_line_total = line.line_total

        # Mutate master Product
        self.product_a.name = "Overhauled Super Product"
        self.product_a.unit_price = Decimal("9999.00")
        self.product_a.gst_rate = Decimal("28.00")
        self.product_a.taxability_type = TaxabilityType.EXEMPT
        self.product_a.save()

        line.refresh_from_db()
        self.assertEqual(line.product_name_snapshot, original_product_name)
        self.assertEqual(line.gst_rate_snapshot, original_gst_rate)
        self.assertEqual(line.taxable_value, original_taxable)
        self.assertEqual(line.line_total, original_line_total)

    # -----------------------------------------------------------------------
    # 19 - 20: Master Record Deletion Safety (SET_NULL)
    # -----------------------------------------------------------------------

    def test_19_customer_deletion_preserves_invoice(self):
        """Deleting Customer master preserves Invoice and its snapshots (FK becomes NULL)."""
        inv_uuid = self.issued_a.uuid
        snap_name = self.issued_a.customer_name_snapshot
        snap_address = self.issued_a.customer_billing_address_snapshot

        self.customer_a.delete()

        inv = Invoice.objects.get(uuid=inv_uuid)
        self.assertIsNone(inv.customer)
        self.assertEqual(inv.customer_name_snapshot, snap_name)
        self.assertEqual(inv.customer_billing_address_snapshot, snap_address)

    def test_20_product_deletion_preserves_invoice_line(self):
        """Deleting Product master preserves InvoiceLine and its snapshots (FK becomes NULL)."""
        line = self.issued_a.lines.first()
        line_id = line.id
        snap_name = line.product_name_snapshot
        snap_rate = line.gst_rate_snapshot
        snap_total = line.line_total

        self.product_a.delete()

        line = InvoiceLine.objects.get(id=line_id)
        self.assertIsNone(line.product)
        self.assertEqual(line.product_name_snapshot, snap_name)
        self.assertEqual(line.gst_rate_snapshot, snap_rate)
        self.assertEqual(line.line_total, snap_total)

    # -----------------------------------------------------------------------
    # 21 - 23: Tampered Inputs & Autoritative Backend Calculations
    # -----------------------------------------------------------------------

    def test_21_tampered_invoice_number_cannot_override_numbering(self):
        """Submitting a custom invoice_number during creation or issue is ignored."""
        post_data = {
            "customer": str(self.customer_a.id),
            "invoice_date": str(datetime.date.today()),
            "shipping_same_as_billing": "on",   # Derive POS from billing state
            "invoice_number": "MALICIOUS-CUSTOM-001",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product_a.id),
            "lines-0-quantity": "1.000",
            "lines-0-unit_price": "1000.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0.00",
        }
        resp = self.client_a.post(reverse("billing:create"), post_data)
        self.assertEqual(resp.status_code, 302)
        created_inv = Invoice.objects.filter(organization=self.org_a).exclude(pk__in=[self.draft_a.pk, self.issued_a.pk]).latest("created_at")
        self.assertEqual(created_inv.invoice_number, "", "Draft invoice should not have manual invoice_number")

        finalize_invoice(created_inv)
        created_inv.refresh_from_db()
        self.assertTrue(created_inv.invoice_number.startswith("ALPHA-"))
        self.assertNotEqual(created_inv.invoice_number, "MALICIOUS-CUSTOM-001")

    def test_22_tampered_totals_cannot_override_backend_calculations(self):
        """Submitting manipulated grand_total, tax_total, or discounts is ignored by the backend engine."""
        draft = Invoice.objects.create(
            organization=self.org_a,
            customer=self.customer_a,
            status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(),
            place_of_supply="27",
            grand_total=Decimal("1.00"),
            taxable_amount=Decimal("1.00"),
            subtotal=Decimal("1.00")
        )
        InvoiceLine.objects.create(
            invoice=draft,
            position=1,
            product=self.product_a,
            quantity=Decimal("2.000"),
            unit_price=Decimal("1000.00"),
            discount_type=DiscountType.NONE,
            discount_value=Decimal("0.00"),
            line_total=Decimal("5.00")
        )
        # Finalize must recalculate 2 * 1000 = 2000 subtotal + 18% GST (360) = 2360 grand total
        finalize_invoice(draft)
        draft.refresh_from_db()
        self.assertEqual(draft.subtotal, Decimal("2000.00"))
        self.assertEqual(draft.taxable_amount, Decimal("2000.00"))
        self.assertEqual(draft.cgst_total, Decimal("180.00"))
        self.assertEqual(draft.sgst_total, Decimal("180.00"))
        self.assertEqual(draft.grand_total, Decimal("2360.00"))

    def test_23_tampered_snapshot_fields_cannot_rewrite_historical_data(self):
        """Direct DB/form tampering of snapshots on draft is overwritten on finalization."""
        draft = Invoice.objects.create(
            organization=self.org_a,
            customer=self.customer_a,
            status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(),
            place_of_supply="27",
            customer_name_snapshot="Fake Spoofed Customer Name"
        )
        InvoiceLine.objects.create(
            invoice=draft,
            position=1,
            product=self.product_a,
            product_name_snapshot="Fake Spoofed Product Name",
            quantity=Decimal("1.000"),
            unit_price=Decimal("1000.00")
        )
        finalize_invoice(draft)
        draft.refresh_from_db()
        self.assertEqual(draft.customer_name_snapshot, self.customer_a.name)
        self.assertEqual(draft.lines.first().product_name_snapshot, self.product_a.name)

    # -----------------------------------------------------------------------
    # 24 - 25: HTTP Method Protection & CSRF Active
    # -----------------------------------------------------------------------

    def test_24_destructive_get_methods_rejected(self):
        """Issue and Cancel endpoints strictly require POST, rejecting GET requests."""
        resp_issue = self.client_a.get(reverse("billing:issue", kwargs={"uuid": self.draft_a.uuid}))
        self.assertEqual(resp_issue.status_code, 405)

        resp_cancel = self.client_a.get(reverse("billing:cancel", kwargs={"uuid": self.issued_a.uuid}))
        self.assertEqual(resp_cancel.status_code, 405)

    def test_25_csrf_protection_remains_active(self):
        """State-changing requests with an unauthenticated or non-CSRF client enforce standard CSRF verification."""
        enforced_client = Client(enforce_csrf_checks=True)
        enforced_client.force_login(self.user_a)
        # Without CSRF token in POST, request should be rejected (403)
        resp = enforced_client.post(
            reverse("billing:issue", kwargs={"uuid": self.draft_a.uuid}),
            {}
        )
        self.assertEqual(resp.status_code, 403)

    # -----------------------------------------------------------------------
    # 26 - 29: API Isolation & Backend Service Boundary Checks
    # -----------------------------------------------------------------------

    def test_26_cross_org_customer_json_api_denied_and_filtered(self):
        """Customer search and detail JSON APIs enforce organization boundaries."""
        # Search API does not return other tenant customers
        resp_search = self.client_a.get(reverse("billing:api_customers"))
        self.assertEqual(resp_search.status_code, 200)
        data = resp_search.json()
        ids = [item["id"] for item in data["results"]]
        self.assertIn(str(self.customer_a.id), ids)
        self.assertNotIn(str(self.customer_b.id), ids)

        # Detail API returns 404 for cross-tenant ID
        resp_detail = self.client_a.get(reverse("billing:api_customer_detail", kwargs={"pk": self.customer_b.pk}))
        self.assertEqual(resp_detail.status_code, 404)

    def test_27_cross_org_product_json_api_filtered(self):
        """Product search JSON API does not return other tenant products."""
        resp = self.client_a.get(reverse("billing:api_products"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        ids = [item["id"] for item in data["results"]]
        self.assertIn(str(self.product_a.id), ids)
        self.assertNotIn(str(self.product_b.id), ids)

    def test_28_cross_org_draft_calculation_preview_denied(self):
        """Calculation preview AJAX endpoint returns 404 when requested on another tenant's invoice."""
        url = reverse("billing:preview_calc", kwargs={"uuid": self.draft_b.uuid})
        resp = self.client_a.post(url, '{"place_of_supply": "27"}', content_type="application/json")
        self.assertEqual(resp.status_code, 404)

    def test_29_direct_backend_service_cross_org_rejection(self):
        """Direct backend service calls reject cross-tenant customer or product objects."""
        # Invoice with Org B customer in Org A
        bad_inv = Invoice(
            organization=self.org_a,
            customer=self.customer_b,
            place_of_supply="27"
        )
        with self.assertRaises(ValidationError) as ctx:
            prepare_invoice_snapshots(bad_inv, [])
        self.assertIn("Customer does not belong to the invoice's organization", str(ctx.exception))

        with self.assertRaises(ValidationError) as ctx:
            validate_invoice(bad_inv)
        self.assertIn("Customer does not belong to the invoice's organization", str(ctx.exception))
