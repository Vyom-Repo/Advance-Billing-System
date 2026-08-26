"""
apps/billing/tests/test_p0_invoice_issuance.py

Regression tests for P0-3: Invoice Issuance with Missing or Existing InvoicePreference.
"""
import datetime
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.organization.models import Organization
from apps.customers.models import Customer
from apps.products.models import Product, TaxabilityType, PriceBasis
from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus
from apps.billing.services.lifecycle import prepare_invoice_snapshots, issue_invoice
from apps.settings_app.models import InvoicePreference

User = get_user_model()


class InvoiceIssuanceP0Tests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fresh_user@example.com",
            email="fresh_user@example.com",
            password="Password123!"
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Fresh Business Private Limited",
            gstin="27CCCCCC2222C1Z3",
            state_code="27"
        )
        self.customer = Customer.objects.create(
            organization=self.org,
            name="Test Customer Ltd",
            gstin="27DDDDD3333D1Z4",
            billing_address_line_1="123 Corporate Park",
            billing_state_code="27"
        )
        self.product = Product.objects.create(
            organization=self.org,
            name="Consulting Services",
            unit_price=Decimal("5000.00"),
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            price_basis=PriceBasis.EXCLUSIVE
        )

    def test_first_invoice_issuance_without_preexisting_preference(self):
        """
        Verify invoice issuance succeeds cleanly when NO InvoicePreference record exists beforehand.
        InvoicePreference should be safely initialized, starting_number incremented, and status changed to ISSUED.
        """
        # Ensure no InvoicePreference exists before issuance
        self.assertFalse(InvoicePreference.objects.filter(user=self.user).exists())

        # Create draft invoice
        invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=datetime.date.today(),
            place_of_supply="27",
            status=InvoiceStatus.DRAFT
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            position=1,
            product=self.product,
            quantity=Decimal("2.00"),
            unit_price=Decimal("5000.00")
        )
        prepare_invoice_snapshots(invoice, [line])
        invoice.save()

        # Issue the invoice
        issued_invoice = issue_invoice(invoice)

        self.assertEqual(issued_invoice.status, InvoiceStatus.ISSUED)
        self.assertTrue(issued_invoice.invoice_number.endswith("-0001"))
        
        # Verify InvoicePreference now exists and starting_number is incremented to 2
        pref = InvoicePreference.objects.get(user=self.user)
        self.assertEqual(pref.starting_number, 2)

    def test_issuance_preserves_existing_custom_preference(self):
        """
        Verify invoice issuance preserves existing InvoicePreference configuration
        (e.g., custom prefix 'INV-CUSTOM' and custom starting_number=100).
        """
        custom_pref = InvoicePreference.objects.create(
            user=self.user,
            invoice_prefix="INV-CUSTOM",
            starting_number=100,
            include_financial_year=False
        )

        invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=datetime.date.today(),
            place_of_supply="27",
            status=InvoiceStatus.DRAFT
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            position=1,
            product=self.product,
            quantity=Decimal("1.00"),
            unit_price=Decimal("5000.00")
        )
        prepare_invoice_snapshots(invoice, [line])
        invoice.save()

        issued_invoice = issue_invoice(invoice)

        self.assertEqual(issued_invoice.status, InvoiceStatus.ISSUED)
        self.assertEqual(issued_invoice.invoice_number, "INV-CUSTOM-0100")

        # Reload preference to verify starting_number was incremented to 101
        custom_pref.refresh_from_db()
        self.assertEqual(custom_pref.starting_number, 101)
        self.assertEqual(custom_pref.invoice_prefix, "INV-CUSTOM")
