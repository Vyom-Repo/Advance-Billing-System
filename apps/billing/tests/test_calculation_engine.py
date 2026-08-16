from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
User = get_user_model()
from apps.billing.models import Organization, Customer, Invoice, InvoiceLine, InvoiceStatus
from apps.products.models import Product, TaxabilityType, PriceBasis
from apps.settings_app.models import InvoicePreference
from apps.billing.services.calculation_engine import validate_invoice, finalize_invoice

class CalculationEngineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='calc', email='calc@example.com', password='password123',
            first_name='Calc', last_name='Engine'
        )
        self.organization = Organization.objects.create(
            business_name="Calc Corp",
            owner=self.user,
            state_code="27"
        )
        self.preference = InvoicePreference.objects.create(
            user=self.user,
            starting_number=1,
            invoice_prefix="INV"
        )
        self.customer = Customer.objects.create(
            organization=self.organization,
            name="Acme Inc",
            billing_state_code="27" # Intra-state (CGST + SGST)
        )
        self.product_taxable_exc = Product.objects.create(
            organization=self.organization,
            name="Laptop",
            unit_price=Decimal('1000.00'),
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal('18.0'),
            price_basis=PriceBasis.EXCLUSIVE
        )
        self.product_taxable_inc = Product.objects.create(
            organization=self.organization,
            name="Mouse",
            unit_price=Decimal('500.00'),
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal('12.0'),
            price_basis=PriceBasis.INCLUSIVE
        )
        import datetime
        self.invoice = Invoice.objects.create(
            organization=self.organization,
            customer=self.customer,
            place_of_supply="27",
            status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today()
        )

    def test_validation_rejects_missing_customer(self):
        self.invoice.customer = None
        self.invoice.save()
        with self.assertRaisesMessage(ValidationError, "Customer is required to finalize the invoice"):
            validate_invoice(self.invoice)

    def test_validation_rejects_empty_lines(self):
        with self.assertRaisesMessage(ValidationError, "Invoice must contain at least one line"):
            validate_invoice(self.invoice)

    def test_calculation_exclusive_taxable(self):
        line = InvoiceLine.objects.create(
            invoice=self.invoice,
            product=self.product_taxable_exc,
            quantity=2,
            unit_price=Decimal('1000.00'),
            position=1
        )
        issued_inv = finalize_invoice(self.invoice)
        line.refresh_from_db()
        
        # 2 * 1000 = 2000
        self.assertEqual(line.line_total, Decimal('2360.00')) # 2000 + 360 tax
        self.assertEqual(line.cgst_amount, Decimal('180.00'))
        self.assertEqual(line.sgst_amount, Decimal('180.00'))
        self.assertEqual(line.igst_amount, Decimal('0.00'))
        
        self.assertEqual(issued_inv.subtotal, Decimal('2000.00'))
        self.assertEqual(issued_inv.cgst_total, Decimal('180.00'))
        self.assertEqual(issued_inv.sgst_total, Decimal('180.00'))
        self.assertEqual(issued_inv.grand_total, Decimal('2360.00'))

    def test_calculation_inclusive_taxable(self):
        line = InvoiceLine.objects.create(
            invoice=self.invoice,
            product=self.product_taxable_inc,
            quantity=2,
            unit_price=Decimal('500.00'),
            position=1
        )
        issued_inv = finalize_invoice(self.invoice)
        line.refresh_from_db()
        
        # 2 * 500 = 1000 (inclusive of 12% GST)
        # Taxable Value = 1000 * 100/112 = 892.86
        # Tax = 1000 - 892.86 = 107.14
        self.assertEqual(line.line_total, Decimal('1000.00'))
        self.assertEqual(line.taxable_value, Decimal('892.86'))
        self.assertEqual(line.cgst_amount, Decimal('53.57'))
        self.assertEqual(line.sgst_amount, Decimal('53.57'))
        
        self.assertEqual(issued_inv.subtotal, Decimal('1000.00'))
        self.assertEqual(issued_inv.taxable_amount, Decimal('892.86'))
        self.assertEqual(issued_inv.cgst_total, Decimal('53.57'))
        self.assertEqual(issued_inv.sgst_total, Decimal('53.57'))
        self.assertEqual(issued_inv.grand_total, Decimal('1000.00'))

    def test_round_off(self):
        # Create a line with an exclusive price of 10.11 and 18% GST -> 10.11 * 1.18 = 11.9298
        Product.objects.create(
            organization=self.organization,
            name="Odd Item",
            unit_price=Decimal('10.11'),
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal('18.0'),
            price_basis=PriceBasis.EXCLUSIVE
        )
        line = InvoiceLine.objects.create(
            invoice=self.invoice,
            product=Product.objects.get(name="Odd Item"),
            quantity=1,
            unit_price=Decimal('10.11'),
            position=1
        )
        issued_inv = finalize_invoice(self.invoice)
        
        # taxable: 10.11
        # cgst (9%): 0.91
        # sgst (9%): 0.91
        # line_total: 10.11 + 0.91 + 0.91 = 11.93
        # Subtotal: 10.11, Total Tax: 1.82, Pre-round: 11.93
        # Round Off = 12.00 - 11.93 = +0.07
        self.assertEqual(issued_inv.subtotal, Decimal('10.11'))
        self.assertEqual(issued_inv.cgst_total, Decimal('0.91'))
        self.assertEqual(issued_inv.sgst_total, Decimal('0.91'))
        self.assertEqual(issued_inv.round_off, Decimal('0.07'))
        self.assertEqual(issued_inv.grand_total, Decimal('12.00'))

    def test_atomicity_rolls_back(self):
        # Create valid line but make issue_invoice fail to test atomic block
        InvoiceLine.objects.create(
            invoice=self.invoice,
            product=self.product_taxable_exc,
            quantity=2,
            unit_price=Decimal('1000.00'),
            position=1
        )
        
        # Tamper with the preference to cause an error when saving
        # Actually an easier way: change status manually so issue_invoice raises ValidationError
        self.invoice.status = InvoiceStatus.ISSUED
        self.invoice.save()
        
        with self.assertRaisesMessage(ValidationError, "Only draft invoices can be issued."):
            finalize_invoice(self.invoice)
            
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.grand_total, Decimal('0.00'))
        self.assertEqual(self.invoice.subtotal, Decimal('0.00'))
