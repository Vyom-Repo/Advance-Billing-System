from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from apps.organization.models import Organization
from apps.customers.models import Customer
from apps.products.models import Product, ProductType, TaxabilityType, PriceBasis
from apps.billing.models import Invoice, InvoiceStatus, InvoiceLine
from apps.billing.forms import InvoiceLineForm
from apps.billing.services.lifecycle import issue_invoice, prepare_invoice_snapshots
from apps.billing.services.calculation_engine import finalize_invoice
from apps.settings_app.models import InvoicePreference

User = get_user_model()

class ProductIntegrationTests(TestCase):
    def setUp(self):
        # Create users and organizations
        self.user1 = User.objects.create_user(username="user1", password="pw")
        self.org1 = Organization.objects.create(business_name="Org 1", owner=self.user1, business_email="1@1.com")
        self.user1.organization_id = self.org1.id
        self.user1.save()

        self.user2 = User.objects.create_user(username="user2", password="pw")
        self.org2 = Organization.objects.create(business_name="Org 2", owner=self.user2, business_email="2@2.com")
        self.user2.organization_id = self.org2.id
        self.user2.save()

        # Create invoice preferences for locking
        InvoicePreference.objects.create(user=self.user1, starting_number=1, invoice_prefix="INV1")
        InvoicePreference.objects.create(user=self.user2, starting_number=1, invoice_prefix="INV2")

        # Create customers
        self.cust1 = Customer.objects.create(
            organization=self.org1, name="Cust 1", billing_state_code="27"
        )

        # Create products
        self.prod1_org1 = Product.objects.create(
            organization=self.org1,
            name="Laptop",
            product_type=ProductType.GOODS,
            hsn_code="8471",
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            unit_price=Decimal("50000.00"),
            uqc="PCS",
            price_basis=PriceBasis.EXCLUSIVE
        )
        self.prod2_org1 = Product.objects.create(
            organization=self.org1,
            name="Consulting",
            product_type=ProductType.SERVICE,
            sac_code="9983",
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            unit_price=Decimal("10000.00"),
            uqc="OTH",
            price_basis=PriceBasis.EXCLUSIVE
        )
        self.prod_org2 = Product.objects.create(
            organization=self.org2,
            name="Org 2 Product",
            product_type=ProductType.GOODS,
            unit_price=Decimal("100.00"),
            uqc="PCS"
        )

        # Create Draft Invoice
        self.invoice = Invoice.objects.create(
            organization=self.org1,
            customer=self.cust1,
            status=InvoiceStatus.DRAFT,
            invoice_date="2026-08-16",
            due_date="2026-08-16",
            place_of_supply="27"
        )

    def test_invoice_line_form_scoping(self):
        # 1. Product belonging to the current organization can be selected.
        form = InvoiceLineForm(
            organization=self.org1,
            data={'product': self.prod1_org1.id, 'quantity': 1, 'unit_price': '50000.00',
                  'discount_type': 'none', 'discount_value': '0.00'}
        )
        self.assertTrue(form.is_valid())

        # 2. Product belonging to another organization cannot be selected.
        form2 = InvoiceLineForm(
            organization=self.org1,
            data={'product': self.prod_org2.id, 'quantity': 1, 'unit_price': '100.00',
                  'discount_type': 'none', 'discount_value': '0.00'}
        )
        self.assertFalse(form2.is_valid())
        self.assertIn('product', form2.errors)

        # 3. Invalid Product UUID is rejected.
        form3 = InvoiceLineForm(
            organization=self.org1,
            data={'product': 99999, 'quantity': 1, 'unit_price': '100.00',
                  'discount_type': 'none', 'discount_value': '0.00'}
        )
        self.assertFalse(form3.is_valid())
        
    def test_invoice_line_form_defaults(self):
        # 4. Product defaults are correctly mapped into InvoiceLine (unit price)
        form = InvoiceLineForm(organization=self.org1, initial={'product': self.prod1_org1.id})
        self.assertEqual(form.fields['unit_price'].initial, Decimal("50000.00"))

    def test_invoice_line_save_defaults(self):
        # Even without form, unit price gets populated
        line = InvoiceLine(
            invoice=self.invoice,
            position=1,
            product=self.prod1_org1,
            quantity=Decimal("2.000")
            # missing unit_price
        )
        line.save()
        self.assertEqual(line.unit_price, self.prod1_org1.unit_price)

    def test_multiple_lines_snapshots(self):
        line1 = InvoiceLine.objects.create(
            invoice=self.invoice, position=1, product=self.prod1_org1,
            quantity=Decimal("1.000"), unit_price=self.prod1_org1.unit_price
        )
        line2 = InvoiceLine.objects.create(
            invoice=self.invoice, position=2, product=self.prod2_org1,
            quantity=Decimal("5.000"), unit_price=self.prod2_org1.unit_price
        )

        finalize_invoice(self.invoice)

        line1.refresh_from_db()
        line2.refresh_from_db()

        self.assertEqual(line1.product_name_snapshot, "Laptop")
        self.assertEqual(line1.hsn_sac_snapshot, "8471")
        self.assertEqual(line1.uqc_snapshot, "PCS")

        self.assertEqual(line2.product_name_snapshot, "Consulting")
        self.assertEqual(line2.hsn_sac_snapshot, "9983")
        self.assertEqual(line2.uqc_snapshot, "OTH")

    def test_quantity_behavior(self):
        # Quantity is stored on InvoiceLine, does not mutate Product master
        line = InvoiceLine.objects.create(
            invoice=self.invoice, position=1, product=self.prod1_org1,
            quantity=Decimal("10.500"), unit_price=Decimal("49000.00")
        )
        self.assertEqual(line.quantity, Decimal("10.500"))
        # Product is unaffected
        self.prod1_org1.refresh_from_db()
        self.assertEqual(self.prod1_org1.unit_price, Decimal("50000.00"))

    def test_draft_product_change(self):
        # Draft InvoiceLine can select Product A
        line = InvoiceLine.objects.create(
            invoice=self.invoice, position=1, product=self.prod1_org1,
            quantity=Decimal("1.000"), unit_price=self.prod1_org1.unit_price
        )

        # Change to Product B before issue
        line.product = self.prod2_org1
        line.save()

        finalize_invoice(self.invoice)
        line.refresh_from_db()

        # Final snapshot should be Product B
        self.assertEqual(line.product_name_snapshot, "Consulting")

    def test_historical_integrity(self):
        line = InvoiceLine.objects.create(
            invoice=self.invoice, position=1, product=self.prod1_org1,
            quantity=Decimal("2.000"), unit_price=self.prod1_org1.unit_price
        )
        
        finalize_invoice(self.invoice)
        line.refresh_from_db()
        
        # Verify initial snapshot
        self.assertEqual(line.product_name_snapshot, "Laptop")
        self.assertEqual(line.gst_rate_snapshot, Decimal("18.00"))
        self.assertEqual(line.unit_price, Decimal("50000.00"))

        # Mutate the product master
        self.prod1_org1.name = "Gaming Laptop"
        self.prod1_org1.gst_rate = Decimal("28.00")
        self.prod1_org1.unit_price = Decimal("60000.00")
        self.prod1_org1.save()

        # Verify issued InvoiceLine remains unchanged
        line.refresh_from_db()
        self.assertEqual(line.product_name_snapshot, "Laptop")
        self.assertEqual(line.gst_rate_snapshot, Decimal("18.00"))
        self.assertEqual(line.unit_price, Decimal("50000.00"))

    def test_product_deletion_in_draft(self):
        line = InvoiceLine.objects.create(
            invoice=self.invoice, position=1, product=self.prod1_org1,
            quantity=Decimal("1.000"), unit_price=self.prod1_org1.unit_price
        )

        # Delete product
        self.prod1_org1.delete()
        
        # Refresh line -> product is now NULL (SET_NULL behavior)
        line.refresh_from_db()
        self.assertIsNone(line.product)

        # Issuing should now be rejected
        with self.assertRaisesMessage(ValidationError, "Product is missing on line 1."):
            finalize_invoice(self.invoice)

    def test_product_deletion_after_issue(self):
        line = InvoiceLine.objects.create(
            invoice=self.invoice, position=1, product=self.prod1_org1,
            quantity=Decimal("1.000"), unit_price=self.prod1_org1.unit_price
        )
        finalize_invoice(self.invoice)

        # Delete product
        self.prod1_org1.delete()

        # Refresh line
        line.refresh_from_db()
        self.assertIsNone(line.product)
        # Snapshot must remain intact
        self.assertEqual(line.product_name_snapshot, "Laptop")

    def test_organization_isolation_in_issue(self):
        # Directly assigning a cross-org product to a line
        line = InvoiceLine.objects.create(
            invoice=self.invoice, position=1, product=self.prod_org2,
            quantity=Decimal("1.000"), unit_price=self.prod_org2.unit_price
        )
        
        # Issuing should be rejected
        with self.assertRaisesMessage(ValidationError, "Product on line 1 does not belong to the invoice's organization."):
            prepare_invoice_snapshots(self.invoice)
            self.invoice.save()
            for line in self.invoice.lines.all(): line.save()
            issue_invoice(self.invoice)
