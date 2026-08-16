from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

from apps.organization.models import Organization
from apps.customers.models import Customer
from apps.products.models import Product, ProductType, TaxabilityType, PriceBasis
from apps.billing.models import Invoice, InvoiceStatus, InvoiceLine, DiscountType
from apps.billing.services.pricing import (
    quantize_money,
    calculate_gross_line_value,
    calculate_discount_amount,
    calculate_net_line_value,
    calculate_tax_exclusive_base_from_inclusive,
    calculate_invoice_pricing_summary,
)

User = get_user_model()


class PricingServiceTests(TestCase):
    def setUp(self):
        # Create users and organizations for DB tests
        self.user1 = User.objects.create_user(username="user1", password="pw")
        self.org1 = Organization.objects.create(business_name="Org 1", owner=self.user1, business_email="1@1.com")
        
        self.cust1 = Customer.objects.create(
            organization=self.org1, name="Cust 1", billing_state_code="27"
        )
        self.prod1 = Product.objects.create(
            organization=self.org1, name="Product 1", unit_price=Decimal("100.00"), uqc="PCS"
        )

        from datetime import date
        self.invoice = Invoice.objects.create(
            organization=self.org1, customer=self.cust1, status=InvoiceStatus.DRAFT, invoice_date=date.today()
        )

    def test_quantize_money(self):
        # Deterministic quantization
        self.assertEqual(quantize_money(Decimal("10.505")), Decimal("10.51"))
        self.assertEqual(quantize_money(Decimal("10.504")), Decimal("10.50"))
        
        # No float allowed
        with self.assertRaises(ValidationError):
            quantize_money(10.50)

    def test_calculate_gross_line_value(self):
        # 1. Quantity x Unit Price
        self.assertEqual(
            calculate_gross_line_value(Decimal("2.000"), Decimal("500.00")),
            Decimal("1000.00")
        )
        # 2. Decimal precision
        self.assertEqual(
            calculate_gross_line_value(Decimal("1.500"), Decimal("10.25")),
            Decimal("15.38")
        )
        # Rejections
        with self.assertRaisesMessage(ValidationError, "Quantity cannot be negative."):
            calculate_gross_line_value(Decimal("-1.000"), Decimal("500.00"))
        
        with self.assertRaisesMessage(ValidationError, "Unit price cannot be negative."):
            calculate_gross_line_value(Decimal("1.000"), Decimal("-500.00"))

    def test_calculate_discount_amount_percentage(self):
        gross = Decimal("1000.00")
        
        # 4. 0%
        self.assertEqual(
            calculate_discount_amount(gross, DiscountType.PERCENTAGE, Decimal("0.00")),
            Decimal("0.00")
        )
        # 5. Normal percentage
        self.assertEqual(
            calculate_discount_amount(gross, DiscountType.PERCENTAGE, Decimal("15.00")),
            Decimal("150.00")
        )
        # 6. 100%
        self.assertEqual(
            calculate_discount_amount(gross, DiscountType.PERCENTAGE, Decimal("100.00")),
            Decimal("1000.00")
        )
        # 7. Negative percentage rejected
        with self.assertRaisesMessage(ValidationError, "Discount value cannot be negative."):
            calculate_discount_amount(gross, DiscountType.PERCENTAGE, Decimal("-10.00"))
            
        # 8. Percentage > 100 rejected
        with self.assertRaisesMessage(ValidationError, "Percentage discount cannot exceed 100%."):
            calculate_discount_amount(gross, DiscountType.PERCENTAGE, Decimal("105.00"))

    def test_calculate_discount_amount_fixed(self):
        gross = Decimal("1000.00")
        
        # 11. Zero fixed discount
        self.assertEqual(
            calculate_discount_amount(gross, DiscountType.FIXED, Decimal("0.00")),
            Decimal("0.00")
        )
        # 12. Normal fixed discount
        self.assertEqual(
            calculate_discount_amount(gross, DiscountType.FIXED, Decimal("150.00")),
            Decimal("150.00")
        )
        # 13. Fixed discount equal to gross
        self.assertEqual(
            calculate_discount_amount(gross, DiscountType.FIXED, Decimal("1000.00")),
            Decimal("1000.00")
        )
        # 14. Negative fixed discount rejected
        with self.assertRaisesMessage(ValidationError, "Discount value cannot be negative."):
            calculate_discount_amount(gross, DiscountType.FIXED, Decimal("-150.00"))
            
        # 15. Fixed discount greater than gross rejected
        with self.assertRaisesMessage(ValidationError, "Fixed discount cannot exceed the gross line value."):
            calculate_discount_amount(gross, DiscountType.FIXED, Decimal("1050.00"))

    def test_calculate_discount_amount_none(self):
        gross = Decimal("1000.00")
        self.assertEqual(
            calculate_discount_amount(gross, DiscountType.NONE, Decimal("999.00")),
            Decimal("0.00")
        )

    def test_calculate_net_line_value(self):
        # Normal
        self.assertEqual(
            calculate_net_line_value(Decimal("1000.00"), Decimal("150.00")),
            Decimal("850.00")
        )
        # Discount > Gross rejected
        with self.assertRaisesMessage(ValidationError, "Discount amount cannot exceed gross value."):
            calculate_net_line_value(Decimal("1000.00"), Decimal("1050.00"))

    def test_calculate_tax_exclusive_base_from_inclusive(self):
        # 18. Inclusive price can be decomposed correctly
        # ₹1180 with 18% GST -> Base ₹1000
        self.assertEqual(
            calculate_tax_exclusive_base_from_inclusive(Decimal("1180.00"), Decimal("18.00")),
            Decimal("1000.00")
        )
        
        # 0% GST inclusive decomposition
        self.assertEqual(
            calculate_tax_exclusive_base_from_inclusive(Decimal("1000.00"), Decimal("0.00")),
            Decimal("1000.00")
        )
        
        # Negative GST rate
        with self.assertRaisesMessage(ValidationError, "GST rate cannot be negative."):
            calculate_tax_exclusive_base_from_inclusive(Decimal("1000.00"), Decimal("-5.00"))

    def test_invoice_aggregation(self):
        # Line 1: Qty 2 x 1000 = 2000, 10% disc = 200, Net = 1800
        InvoiceLine.objects.create(
            invoice=self.invoice, position=1, product=self.prod1,
            quantity=Decimal("2.000"), unit_price=Decimal("1000.00"),
            discount_type=DiscountType.PERCENTAGE, discount_value=Decimal("10.00")
        )
        # Line 2: Qty 3 x 500 = 1500, Fixed disc = 100, Net = 1400
        InvoiceLine.objects.create(
            invoice=self.invoice, position=2, product=self.prod1,
            quantity=Decimal("3.000"), unit_price=Decimal("500.00"),
            discount_type=DiscountType.FIXED, discount_value=Decimal("100.00")
        )

        # Calculate invoice summary
        summary = calculate_invoice_pricing_summary(self.invoice)
        
        self.assertEqual(summary["gross_subtotal"], Decimal("3500.00"))
        self.assertEqual(summary["total_discount"], Decimal("300.00"))
        self.assertEqual(summary["net_transaction_value"], Decimal("3200.00"))
        
        # Ensure it doesn't write to DB
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.subtotal, Decimal("0.00"))
        self.assertEqual(self.invoice.discount_total, Decimal("0.00"))

    def test_historical_transaction_behavior(self):
        line = InvoiceLine.objects.create(
            invoice=self.invoice, position=1, product=self.prod1,
            quantity=Decimal("1.000"), unit_price=self.prod1.unit_price
        )
        
        # Change product master unit price
        self.prod1.unit_price = Decimal("200.00")
        self.prod1.save()
        
        # Refresh line, unit price should remain 100
        line.refresh_from_db()
        self.assertEqual(line.unit_price, Decimal("100.00"))

        summary = calculate_invoice_pricing_summary(self.invoice)
        self.assertEqual(summary["gross_subtotal"], Decimal("100.00"))
