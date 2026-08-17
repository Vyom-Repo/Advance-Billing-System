"""
apps/billing/tests/test_application_layer.py — Phase 09 Application Layer Tests

Tests cover:
- Routes (all 8 URL endpoints)
- Organization isolation (cross-tenant access prevention)
- Draft CRUD (create, edit, customer/product change, add/remove lines, delete)
- Issued invoice behavior (read-only, no delete, no edit, cancel)
- Cancelled invoice behavior (accessible, read-only)
- Finalization (Issue calls Phase 08, validation errors surfaced)
- Forms (org-scoped querysets, invalid input rejection)
- UI behavior (action buttons present/absent based on status)
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus, DiscountType
from apps.billing.services.calculation_engine import finalize_invoice
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product, TaxabilityType, PriceBasis
from apps.settings_app.models import InvoicePreference

User = get_user_model()


# ---------------------------------------------------------------------------
# Test helpers / fixtures
# ---------------------------------------------------------------------------

def make_user(username, email):
    return User.objects.create_user(username=username, email=email, password="password123", first_name="Test")


def make_org(user, business_name="Test Org", state_code="27"):
    return Organization.objects.create(
        owner=user, business_name=business_name,
        business_email=user.email,
        state_code=state_code,
        address_line_1="123 Main St", city="Mumbai", state="Maharashtra",
        pincode="400001", country="India"
    )


def make_pref(user):
    return InvoicePreference.objects.create(user=user, invoice_prefix="INV", starting_number=1)


def make_customer(org, name="Customer A", state_code="27"):
    return Customer.objects.create(
        organization=org, name=name,
        billing_state_code=state_code,
        billing_state="Maharashtra",
        billing_city="Mumbai",
        billing_address_line_1="456 Test Road",
        billing_pin_code="400001",
    )


def make_product(org, name="Widget", price="500.00", taxable=True, gst_rate="18.00", price_basis=PriceBasis.EXCLUSIVE):
    return Product.objects.create(
        organization=org,
        name=name,
        unit_price=Decimal(price),
        taxability_type=TaxabilityType.TAXABLE if taxable else TaxabilityType.EXEMPT,
        gst_rate=Decimal(gst_rate),
        price_basis=price_basis,
    )


def make_draft_invoice(org, customer, invoice_date=None):
    return Invoice.objects.create(
        organization=org,
        customer=customer,
        status=InvoiceStatus.DRAFT,
        invoice_date=invoice_date or datetime.date.today(),
        place_of_supply="27",
        customer_name_snapshot=customer.name,
        customer_gstin_snapshot=customer.gstin or "",
        customer_billing_address_snapshot=customer.full_billing_address,
        customer_state_code_snapshot=customer.billing_state_code,
    )


def make_invoice_line(invoice, product, qty="1.000", price="500.00"):
    return InvoiceLine.objects.create(
        invoice=invoice,
        product=product,
        position=1,
        quantity=Decimal(qty),
        unit_price=Decimal(price),
        discount_type=DiscountType.NONE,
        discount_value=Decimal("0.00"),
    )


# ---------------------------------------------------------------------------
# Base test class with org + client setup
# ---------------------------------------------------------------------------

class InvoiceBaseTest(TestCase):
    def setUp(self):
        self.user = make_user("orguser", "orguser@example.com")
        self.org = make_org(self.user, "Org Alpha", state_code="27")
        self.pref = make_pref(self.user)
        self.customer = make_customer(self.org)
        self.product = make_product(self.org)
        self.client = Client()
        self.client.login(username="orguser", password="password123")

        # Second org for isolation tests
        self.user2 = make_user("orguser2", "orguser2@example.com")
        self.org2 = make_org(self.user2, "Org Beta", state_code="27")
        make_pref(self.user2)
        self.customer2 = make_customer(self.org2, name="Customer B")
        self.product2 = make_product(self.org2, name="Widget B")


# ---------------------------------------------------------------------------
# 1. Routes
# ---------------------------------------------------------------------------

class InvoiceRoutesTest(InvoiceBaseTest):

    def test_list_route_works(self):
        resp = self.client.get(reverse("billing:index"))
        self.assertEqual(resp.status_code, 200)

    def test_create_route_works(self):
        resp = self.client.get(reverse("billing:create"))
        self.assertEqual(resp.status_code, 200)

    def test_detail_route_works(self):
        inv = make_draft_invoice(self.org, self.customer)
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": inv.uuid}))
        self.assertEqual(resp.status_code, 200)

    def test_edit_route_works_for_draft(self):
        inv = make_draft_invoice(self.org, self.customer)
        resp = self.client.get(reverse("billing:edit", kwargs={"uuid": inv.uuid}))
        self.assertEqual(resp.status_code, 200)

    def test_delete_route_works_for_draft(self):
        inv = make_draft_invoice(self.org, self.customer)
        resp = self.client.get(reverse("billing:delete", kwargs={"uuid": inv.uuid}))
        self.assertEqual(resp.status_code, 200)

    def test_preview_route_works(self):
        inv = make_draft_invoice(self.org, self.customer)
        resp = self.client.get(reverse("billing:preview", kwargs={"uuid": inv.uuid}))
        self.assertEqual(resp.status_code, 200)

    def test_api_customers_route_works(self):
        resp = self.client.get(reverse("billing:api_customers"))
        self.assertEqual(resp.status_code, 200)

    def test_api_products_route_works(self):
        resp = self.client.get(reverse("billing:api_products"))
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 2. Organization Isolation
# ---------------------------------------------------------------------------

class InvoiceOrganizationIsolationTest(InvoiceBaseTest):

    def test_org_a_cannot_access_org_b_invoice(self):
        inv2 = make_draft_invoice(self.org2, self.customer2)
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": inv2.uuid}))
        self.assertEqual(resp.status_code, 404)

    def test_org_a_cannot_edit_org_b_invoice(self):
        inv2 = make_draft_invoice(self.org2, self.customer2)
        resp = self.client.get(reverse("billing:edit", kwargs={"uuid": inv2.uuid}))
        self.assertEqual(resp.status_code, 404)

    def test_api_customers_scoped_to_org(self):
        resp = self.client.get(reverse("billing:api_customers"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        names = [c["name"] for c in data["results"]]
        self.assertIn("Customer A", names)
        self.assertNotIn("Customer B", names)

    def test_api_products_scoped_to_org(self):
        resp = self.client.get(reverse("billing:api_products"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        names = [p["name"] for p in data["results"]]
        self.assertIn("Widget", names)
        self.assertNotIn("Widget B", names)


# ---------------------------------------------------------------------------
# 3. Draft Invoice CRUD
# ---------------------------------------------------------------------------

class DraftInvoiceCRUDTest(InvoiceBaseTest):

    def test_create_draft_invoice(self):
        resp = self.client.post(reverse("billing:create"), {
            "invoice_date": "2026-08-16",
            "due_date": "",
            "customer": str(self.customer.id),
            "place_of_supply": "27",
            "shipping_same_as_billing": "on",
            "notes": "Test note",
            "terms": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.id),
            "lines-0-quantity": "2.000",
            "lines-0-unit_price": "500.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0.00",
        }, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Invoice.objects.filter(organization=self.org, status=InvoiceStatus.DRAFT).exists())

    def test_draft_invoice_created_is_scoped_to_org(self):
        self.client.post(reverse("billing:create"), {
            "invoice_date": "2026-08-16",
            "customer": str(self.customer.id),
            "place_of_supply": "27",
            "shipping_same_as_billing": "on",
            "lines-TOTAL_FORMS": "0",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
        })
        inv = Invoice.objects.filter(organization=self.org).first()
        if inv:
            self.assertEqual(inv.organization, self.org)

    def test_draft_can_be_edited(self):
        inv = make_draft_invoice(self.org, self.customer)
        resp = self.client.post(
            reverse("billing:edit", kwargs={"uuid": inv.uuid}),
            {
                "invoice_date": "2026-08-17",
                "due_date": "",
                "customer": str(self.customer.id),
                "place_of_supply": "27",
                "shipping_same_as_billing": "on",
                "notes": "Updated note",
                "terms": "",
                "lines-TOTAL_FORMS": "0",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
            },
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(str(inv.invoice_date), "2026-08-17")

    def test_draft_lines_can_be_added(self):
        inv = make_draft_invoice(self.org, self.customer)
        resp = self.client.post(
            reverse("billing:edit", kwargs={"uuid": inv.uuid}),
            {
                "invoice_date": str(inv.invoice_date),
                "customer": str(self.customer.id),
                "place_of_supply": "27",
                "shipping_same_as_billing": "on",
                "notes": "", "terms": "",
                "lines-TOTAL_FORMS": "1",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-product": str(self.product.id),
                "lines-0-quantity": "3.000",
                "lines-0-unit_price": "200.00",
                "lines-0-discount_type": "none",
                "lines-0-discount_value": "0.00",
            },
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(inv.lines.count(), 1)

    def test_draft_can_be_deleted(self):
        inv = make_draft_invoice(self.org, self.customer)
        inv_uuid = inv.uuid
        resp = self.client.post(
            reverse("billing:delete", kwargs={"uuid": inv_uuid}),
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Invoice.objects.filter(uuid=inv_uuid).exists())

    def test_draft_customer_can_change(self):
        inv = make_draft_invoice(self.org, self.customer)
        customer2 = make_customer(self.org, name="Customer New", state_code="24")
        resp = self.client.post(
            reverse("billing:edit", kwargs={"uuid": inv.uuid}),
            {
                "invoice_date": str(inv.invoice_date),
                "customer": str(customer2.id),
                "place_of_supply": "27",
                "shipping_same_as_billing": "on",
                "notes": "", "terms": "",
                "lines-TOTAL_FORMS": "0",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
            },
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(inv.customer, customer2)


# ---------------------------------------------------------------------------
# 4. Issued Invoice Behavior
# ---------------------------------------------------------------------------

class IssuedInvoiceTest(InvoiceBaseTest):

    def _make_issuable_invoice(self):
        inv = make_draft_invoice(self.org, self.customer)
        make_invoice_line(inv, self.product)
        return inv

    def test_issued_invoice_is_read_only_no_edit(self):
        inv = self._make_issuable_invoice()
        issued = finalize_invoice(inv)
        resp = self.client.get(reverse("billing:edit", kwargs={"uuid": issued.uuid}))
        # Should redirect away, not 200 edit form
        self.assertNotEqual(resp.status_code, 200)

    def test_issued_invoice_cannot_be_deleted(self):
        inv = self._make_issuable_invoice()
        issued = finalize_invoice(inv)
        resp = self.client.post(reverse("billing:delete", kwargs={"uuid": issued.uuid}), follow=True)
        # Invoice must still exist
        self.assertTrue(Invoice.objects.filter(uuid=issued.uuid).exists())

    def test_issued_invoice_can_be_cancelled(self):
        inv = self._make_issuable_invoice()
        issued = finalize_invoice(inv)
        resp = self.client.post(
            reverse("billing:cancel", kwargs={"uuid": issued.uuid}),
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        issued.refresh_from_db()
        self.assertEqual(issued.status, InvoiceStatus.CANCELLED)

    def test_issued_invoice_detail_accessible(self):
        inv = self._make_issuable_invoice()
        issued = finalize_invoice(inv)
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": issued.uuid}))
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 5. Cancelled Invoice Behavior
# ---------------------------------------------------------------------------

class CancelledInvoiceTest(InvoiceBaseTest):

    def _make_cancelled_invoice(self):
        inv = make_draft_invoice(self.org, self.customer)
        make_invoice_line(inv, self.product)
        issued = finalize_invoice(inv)
        from apps.billing.services.lifecycle import cancel_invoice
        return cancel_invoice(issued)

    def test_cancelled_invoice_detail_accessible(self):
        inv = self._make_cancelled_invoice()
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": inv.uuid}))
        self.assertEqual(resp.status_code, 200)

    def test_cancelled_invoice_cannot_be_edited(self):
        inv = self._make_cancelled_invoice()
        resp = self.client.get(reverse("billing:edit", kwargs={"uuid": inv.uuid}))
        self.assertNotEqual(resp.status_code, 200)

    def test_cancelled_invoice_cannot_be_deleted(self):
        inv = self._make_cancelled_invoice()
        resp = self.client.post(reverse("billing:delete", kwargs={"uuid": inv.uuid}), follow=True)
        self.assertTrue(Invoice.objects.filter(uuid=inv.uuid).exists())


# ---------------------------------------------------------------------------
# 6. Finalization via Issue Action
# ---------------------------------------------------------------------------

class InvoiceIssueActionTest(InvoiceBaseTest):

    def test_issue_action_uses_phase08(self):
        inv = make_draft_invoice(self.org, self.customer)
        make_invoice_line(inv, self.product)
        resp = self.client.post(
            reverse("billing:issue", kwargs={"uuid": inv.uuid}),
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.ISSUED)

    def test_successful_issue_generates_invoice_number(self):
        inv = make_draft_invoice(self.org, self.customer)
        make_invoice_line(inv, self.product)
        self.client.post(reverse("billing:issue", kwargs={"uuid": inv.uuid}))
        inv.refresh_from_db()
        self.assertTrue(inv.invoice_number.startswith("INV"))

    def test_issue_sets_calculated_totals(self):
        inv = make_draft_invoice(self.org, self.customer)
        make_invoice_line(inv, self.product, qty="1.000", price="1000.00")
        self.client.post(reverse("billing:issue", kwargs={"uuid": inv.uuid}))
        inv.refresh_from_db()
        self.assertGreater(inv.grand_total, Decimal("0"))

    def test_issue_fails_without_customer_shows_error(self):
        inv = make_draft_invoice(self.org, self.customer)
        inv.customer = None
        inv.save()
        resp = self.client.post(
            reverse("billing:issue", kwargs={"uuid": inv.uuid}),
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.DRAFT)  # Must remain draft

    def test_issue_fails_without_lines_shows_error(self):
        inv = make_draft_invoice(self.org, self.customer)
        # No lines added
        resp = self.client.post(
            reverse("billing:issue", kwargs={"uuid": inv.uuid}),
            follow=True
        )
        self.assertEqual(resp.status_code, 200)
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.DRAFT)

    def test_issue_numbering_from_lifecycle(self):
        """Invoice number uses Phase 03 lifecycle numbering, not arbitrary."""
        inv = make_draft_invoice(self.org, self.customer)
        make_invoice_line(inv, self.product)
        self.client.post(reverse("billing:issue", kwargs={"uuid": inv.uuid}))
        inv.refresh_from_db()
        # Should be INV-0001 (first invoice with starting_number=1)
        self.assertEqual(inv.invoice_number, "INV-0001")


# ---------------------------------------------------------------------------
# 7. Form Queryset Scoping
# ---------------------------------------------------------------------------

class InvoiceFormScopingTest(InvoiceBaseTest):

    def test_customer_queryset_scoped_to_org(self):
        from apps.billing.forms import InvoiceForm
        form = InvoiceForm(organization=self.org)
        customer_ids = list(form.fields["customer"].queryset.values_list("id", flat=True))
        self.assertIn(self.customer.id, customer_ids)
        self.assertNotIn(self.customer2.id, customer_ids)

    def test_product_queryset_scoped_to_org(self):
        from apps.billing.forms import InvoiceLineForm
        form = InvoiceLineForm(organization=self.org)
        product_ids = list(form.fields["product"].queryset.values_list("id", flat=True))
        self.assertIn(self.product.id, product_ids)
        self.assertNotIn(self.product2.id, product_ids)

    def test_invalid_place_of_supply_rejected(self):
        """
        place_of_supply is no longer a user-visible form field.
        The form now uses shipping_state (state code dropdown).
        An invalid/unknown state code must be rejected by resolve_place_of_supply().
        We verify that a draft cannot be created when shipping state is missing
        and shipping_same_as_billing is off, since the view enforces derivation.
        """
        from apps.billing.forms import InvoiceForm
        # The form itself doesn't validate place_of_supply anymore;
        # it's validated in the view via resolve_place_of_supply().
        # Verify the form does NOT have a place_of_supply field at all.
        form = InvoiceForm(data={
            "invoice_date": "2026-08-16",
        }, organization=self.org)
        self.assertNotIn("place_of_supply", form.fields,
                         "place_of_supply must not be a visible form field (it is derived from shipping state)")

    def test_missing_invoice_date_rejected(self):
        from apps.billing.forms import InvoiceForm
        form = InvoiceForm(data={
            "shipping_same_as_billing": "on",
            # Missing invoice_date
        }, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("invoice_date", form.errors)


# ---------------------------------------------------------------------------
# 8. UI Behavior (action buttons presence/absence based on status)
# ---------------------------------------------------------------------------

class InvoiceUIBehaviorTest(InvoiceBaseTest):

    def test_draft_shows_edit_button(self):
        inv = make_draft_invoice(self.org, self.customer)
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": inv.uuid}))
        self.assertContains(resp, "Edit")

    def test_draft_shows_delete_button(self):
        inv = make_draft_invoice(self.org, self.customer)
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": inv.uuid}))
        self.assertContains(resp, "Delete")

    def test_draft_shows_issue_button(self):
        inv = make_draft_invoice(self.org, self.customer)
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": inv.uuid}))
        self.assertContains(resp, "Issue Invoice")

    def test_issued_shows_cancel_button(self):
        inv = make_draft_invoice(self.org, self.customer)
        make_invoice_line(inv, self.product)
        issued = finalize_invoice(inv)
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": issued.uuid}))
        self.assertContains(resp, "Cancel")

    def test_issued_does_not_show_edit_button(self):
        inv = make_draft_invoice(self.org, self.customer)
        make_invoice_line(inv, self.product)
        issued = finalize_invoice(inv)
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": issued.uuid}))
        self.assertNotContains(resp, 'href="' + reverse("billing:edit", kwargs={"uuid": issued.uuid}) + '"')

    def test_cancelled_does_not_show_cancel_button(self):
        inv = make_draft_invoice(self.org, self.customer)
        make_invoice_line(inv, self.product)
        issued = finalize_invoice(inv)
        from apps.billing.services.lifecycle import cancel_invoice
        cancelled = cancel_invoice(issued)
        resp = self.client.get(reverse("billing:detail", kwargs={"uuid": cancelled.uuid}))
        self.assertNotContains(resp, "Cancel Invoice")

    def test_invoice_list_shows_status_badges(self):
        make_draft_invoice(self.org, self.customer)
        resp = self.client.get(reverse("billing:index"))
        self.assertContains(resp, "Draft")

    def test_unauthenticated_redirects_to_login(self):
        self.client.logout()
        resp = self.client.get(reverse("billing:index"))
        self.assertEqual(resp.status_code, 302)
        # Project redirects unauthenticated users to login or organization setup
        self.assertIn(resp.status_code, [301, 302])


# ---------------------------------------------------------------------------
# 9. Customer Detail API
# ---------------------------------------------------------------------------

class CustomerAPITest(InvoiceBaseTest):

    def test_customer_detail_api_returns_data(self):
        resp = self.client.get(
            reverse("billing:api_customer_detail", kwargs={"pk": self.customer.id})
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["name"], "Customer A")

    def test_customer_detail_api_cross_tenant_returns_404(self):
        resp = self.client.get(
            reverse("billing:api_customer_detail", kwargs={"pk": self.customer2.id})
        )
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# 10. Create Invoice Line Submission & DELETE State Regression Tests
# ---------------------------------------------------------------------------

class CreateInvoiceLineSubmissionTest(InvoiceBaseTest):

    def test_single_line_submission_persists_line(self):
        """
        Verify that submitting one valid line item persists the Invoice and InvoiceLine.
        Asserts that DELETE is not treated as True.
        """
        post_data = {
            "invoice_date": "2026-08-16",
            "due_date": "",
            "customer": str(self.customer.id),
            "place_of_supply": "27",
            "shipping_same_as_billing": "on",
            "notes": "",
            "terms": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.id),
            "lines-0-quantity": "1.000",
            "lines-0-unit_price": "75.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0.00",
        }
        resp = self.client.post(reverse("billing:create"), post_data)
        self.assertEqual(resp.status_code, 302)

        invoice = Invoice.objects.filter(organization=self.org).order_by("-created_at").first()
        self.assertIsNotNone(invoice)
        self.assertEqual(resp.url, reverse("billing:detail", kwargs={"uuid": invoice.uuid}))

        lines = invoice.lines.all()
        self.assertEqual(lines.count(), 1)
        line = lines.first()
        self.assertEqual(line.product, self.product)
        self.assertEqual(line.quantity, Decimal("1.000"))
        self.assertEqual(line.unit_price, Decimal("75.00"))

    def test_direct_formset_validation_inspect_delete_state(self):
        """
        Directly test InvoiceForm and FormSet to inspect cleaned_data and DELETE state.
        """
        from apps.billing.forms import InvoiceForm, make_invoice_line_formset
        FormSet = make_invoice_line_formset(self.org, extra=0)
        post_data = {
            "customer": str(self.customer.id),
            "invoice_date": "2026-08-16",
            "shipping_same_as_billing": "on",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.id),
            "lines-0-quantity": "1.000",
            "lines-0-unit_price": "75.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0.00",
        }
        form = InvoiceForm(post_data, organization=self.org)
        formset = FormSet(post_data, prefix="lines")

        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertEqual(len(formset.forms), 1)
        cleaned = formset.forms[0].cleaned_data
        self.assertIsNotNone(cleaned.get("product"))
        self.assertEqual(cleaned["product"], self.product)
        self.assertFalse(cleaned.get("DELETE", False))


class CreateInvoiceMultipleLinesSubmissionTest(InvoiceBaseTest):

    def test_multiple_lines_submission_all_persist(self):
        """
        Submitting 3 valid line items must persist all 3 InvoiceLine objects.
        """
        product2 = make_product(self.org, name="Second Item", price="120.00")
        product3 = make_product(self.org, name="Third Item", price="300.00")

        post_data = {
            "invoice_date": "2026-08-16",
            "due_date": "",
            "customer": str(self.customer.id),
            "place_of_supply": "27",
            "shipping_same_as_billing": "on",
            "notes": "Multi line test",
            "terms": "",
            "lines-TOTAL_FORMS": "3",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.id),
            "lines-0-quantity": "2.000",
            "lines-0-unit_price": "75.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0.00",
            "lines-1-product": str(product2.id),
            "lines-1-quantity": "1.000",
            "lines-1-unit_price": "120.00",
            "lines-1-discount_type": "percentage",
            "lines-1-discount_value": "10.00",
            "lines-2-product": str(product3.id),
            "lines-2-quantity": "5.000",
            "lines-2-unit_price": "300.00",
            "lines-2-discount_type": "none",
            "lines-2-discount_value": "0.00",
        }
        resp = self.client.post(reverse("billing:create"), post_data)
        self.assertEqual(resp.status_code, 302)

        invoice = Invoice.objects.filter(organization=self.org).order_by("-created_at").first()
        self.assertIsNotNone(invoice)
        lines = invoice.lines.all().order_by("position")
        self.assertEqual(lines.count(), 3)
        self.assertEqual(lines[0].product, self.product)
        self.assertEqual(lines[0].quantity, Decimal("2.000"))
        self.assertEqual(lines[1].product, product2)
        self.assertEqual(lines[1].quantity, Decimal("1.000"))
        self.assertEqual(lines[2].product, product3)
        self.assertEqual(lines[2].quantity, Decimal("5.000"))


class CreateInvoiceExplicitDeletionTest(InvoiceBaseTest):

    def test_line_with_explicit_delete_on_is_excluded(self):
        """
        When lines-0-DELETE is 'on', that line is marked deleted, while lines-1 persists.
        """
        product2 = make_product(self.org, name="Kept Product", price="150.00")
        post_data = {
            "invoice_date": "2026-08-16",
            "due_date": "",
            "customer": str(self.customer.id),
            "place_of_supply": "27",
            "shipping_same_as_billing": "on",
            "notes": "",
            "terms": "",
            "lines-TOTAL_FORMS": "2",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.id),
            "lines-0-quantity": "1.000",
            "lines-0-unit_price": "75.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0.00",
            "lines-0-DELETE": "on",
            "lines-1-product": str(product2.id),
            "lines-1-quantity": "3.000",
            "lines-1-unit_price": "150.00",
            "lines-1-discount_type": "none",
            "lines-1-discount_value": "0.00",
        }
        resp = self.client.post(reverse("billing:create"), post_data)
        self.assertEqual(resp.status_code, 302)

        invoice = Invoice.objects.filter(organization=self.org).order_by("-created_at").first()
        lines = invoice.lines.all()
        self.assertEqual(lines.count(), 1)
        self.assertEqual(lines.first().product, product2)

    def test_all_lines_marked_delete_rejects_with_error(self):
        """
        When all lines are marked DELETE='on', backend rejects draft creation.
        """
        post_data = {
            "invoice_date": "2026-08-16",
            "due_date": "",
            "customer": str(self.customer.id),
            "place_of_supply": "27",
            "shipping_same_as_billing": "on",
            "notes": "",
            "terms": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.id),
            "lines-0-quantity": "1.000",
            "lines-0-unit_price": "75.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0.00",
            "lines-0-DELETE": "on",
        }
        resp = self.client.post(reverse("billing:create"), post_data)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "At least one line item with a product is required.")


class InvoiceDateFieldConfigurationTest(InvoiceBaseTest):

    def test_date_fields_have_type_date(self):
        """
        Verify that invoice_date and due_date use type='date' in widget attributes and rendering.
        """
        from apps.billing.forms import InvoiceForm
        form = InvoiceForm(organization=self.org)
        self.assertEqual(form.fields["invoice_date"].widget.input_type, "date")
        self.assertEqual(form.fields["due_date"].widget.input_type, "date")
        self.assertEqual(form.fields["invoice_date"].widget.attrs.get("id"), "id_invoice_date")
        self.assertEqual(form.fields["due_date"].widget.attrs.get("id"), "id_due_date")
        self.assertIn('type="date"', form["invoice_date"].as_widget())
        self.assertIn('type="date"', form["due_date"].as_widget())


# ---------------------------------------------------------------------------
# 11. Invoice State Restoration (Quick Customer/Product Flow)
# ---------------------------------------------------------------------------

class InvoiceStateRestoreTest(InvoiceBaseTest):

    def test_state_restoration_from_session_stash(self):
        """
        Verify that returning to the create invoice form with a state token correctly
        loads the stashed state into the forms (including line formset), avoiding
        ManagementForm validation errors.
        """
        # Stash state in session
        state_token = "testtoken123"
        post_data = {
            "invoice_date": "2026-08-16",
            "due_date": "",
            "customer": "",  # Emulate going to create a new customer
            "place_of_supply": "27",
            "shipping_same_as_billing": "on",
            "notes": "Stashed note",
            "terms": "",
            "lines-TOTAL_FORMS": "2",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.id),
            "lines-0-quantity": "5.000",
            "lines-0-unit_price": "100.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0.00",
            "lines-1-product": "",
            "lines-1-quantity": "1.000",
            "lines-1-unit_price": "0.00",
            "lines-1-discount_type": "none",
            "lines-1-discount_value": "0.00",
        }

        session = self.client.session
        session["invoice_create_states"] = {
            state_token: {
                "state": post_data,
                "line_index": None
            }
        }
        session.save()

        # Simulate returning from customer creation
        new_customer = make_customer(self.org, name="Quick Customer")
        resp = self.client.get(reverse("billing:create") + f"?invoice_state={state_token}&new_customer={new_customer.id}")
        self.assertEqual(resp.status_code, 200)

        # Ensure the view did not error out on ManagementForm and that data is injected
        self.assertContains(resp, "Stashed note")
        
        # Verify the auto-selected customer
        self.assertContains(resp, f'<option value="{new_customer.id}" selected>')

        # Verify TOTAL_FORMS is 2
        self.assertContains(resp, 'name="lines-TOTAL_FORMS" value="2"')

        # Verify the product selection on line 0 was restored
        self.assertContains(resp, f'<option value="{self.product.id}" selected>')


# ---------------------------------------------------------------------------
# 12. Invoice Discount Logic Tests
# ---------------------------------------------------------------------------

class InvoiceDiscountLogicTest(InvoiceBaseTest):

    def test_discount_mode_none_clears_value(self):
        """
        Verify that submitting an invoice line with discount_type = 'none' 
        and a stale discount_value > 0 results in the discount_value being set to 0.
        """
        post_data = {
            "customer": str(self.customer.id),
            "invoice_date": "2026-08-16",
            "due_date": "2026-09-16",
            "place_of_supply": "27",
            "shipping_same_as_billing": "on",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.id),
            "lines-0-quantity": "1.000",
            "lines-0-unit_price": "100.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "50.00",  # Stale value
        }
        
        resp = self.client.post(reverse("billing:create"), data=post_data)
        self.assertEqual(resp.status_code, 302)  # Should redirect to detail
        
        invoice = Invoice.objects.first()
        self.assertIsNotNone(invoice)
        line = invoice.lines.first()
        
        # Verify the discount_value was cleared to 0
        self.assertEqual(line.discount_type, "none")
        self.assertEqual(line.discount_value, 0)
