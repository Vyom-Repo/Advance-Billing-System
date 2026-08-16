from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError

from apps.products.models import TaxabilityType, PriceBasis, CessType
from apps.billing.models import Invoice, InvoiceLine, DiscountType
from apps.billing.services.gst_engine import calculate_line_tax, aggregate_invoice_taxes
from apps.organization.models import Organization
from django.contrib.auth import get_user_model

User = get_user_model()


class GSTEngineTests(TestCase):
    def setUp(self):
        # We don't necessarily need a full DB setup just for the GST engine tests,
        # but since calculate_line_tax takes an InvoiceLine model, we create some basic records.
        self.user = User.objects.create_user(username="test_gst", password="pw")
        self.org = Organization.objects.create(
            business_name="Test Org", 
            owner=self.user, 
            state_code="27" # Maharashtra
        )
        
        self.invoice_intra = Invoice.objects.create(
            organization=self.org,
            invoice_date="2026-08-16",
            place_of_supply="27"
        )
        
        self.invoice_inter = Invoice.objects.create(
            organization=self.org,
            invoice_date="2026-08-16",
            place_of_supply="29" # Karnataka
        )
        
    def _create_line(self, invoice, **kwargs):
        defaults = {
            'position': 1,
            'quantity': 2,
            'unit_price': Decimal('1000.00'),
            'discount_type': DiscountType.NONE,
            'discount_value': Decimal('0.00'),
            'taxability_type_snapshot': TaxabilityType.TAXABLE,
            'gst_rate_snapshot': Decimal('18.00'),
            'price_basis_snapshot': PriceBasis.EXCLUSIVE,
            'cess_applicable_snapshot': False,
            'reverse_charge_snapshot': False,
        }
        defaults.update(kwargs)
        return InvoiceLine.objects.create(invoice=invoice, **defaults)

    def test_taxability_taxable_intra_state(self):
        line = self._create_line(self.invoice_intra)
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        self.assertEqual(result["taxability_type"], TaxabilityType.TAXABLE)
        self.assertEqual(result["taxable_value"], Decimal("2000.00")) # 2 * 1000
        self.assertEqual(result["cgst_amount"], Decimal("180.00")) # 9% of 2000
        self.assertEqual(result["sgst_amount"], Decimal("180.00"))
        self.assertEqual(result["igst_amount"], Decimal("0.00"))
        self.assertEqual(result["total_gst"], Decimal("360.00"))
        self.assertEqual(result["total_tax"], Decimal("360.00"))
        self.assertEqual(result["cess_amount"], Decimal("0.00"))
        self.assertEqual(result["reverse_charge"], False)

    def test_taxability_taxable_inter_state(self):
        line = self._create_line(self.invoice_inter)
        result = calculate_line_tax(line, self.org.state_code, self.invoice_inter.place_of_supply)
        
        self.assertEqual(result["taxable_value"], Decimal("2000.00"))
        self.assertEqual(result["cgst_amount"], Decimal("0.00"))
        self.assertEqual(result["sgst_amount"], Decimal("0.00"))
        self.assertEqual(result["igst_amount"], Decimal("360.00")) # 18% of 2000
        self.assertEqual(result["total_gst"], Decimal("360.00"))
        self.assertEqual(result["total_tax"], Decimal("360.00"))

    def test_taxability_exempt(self):
        line = self._create_line(self.invoice_intra, taxability_type_snapshot=TaxabilityType.EXEMPT, gst_rate_snapshot=Decimal('0.00'))
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        self.assertEqual(result["taxability_type"], TaxabilityType.EXEMPT)
        self.assertEqual(result["taxable_value"], Decimal("2000.00"))
        self.assertEqual(result["cgst_amount"], Decimal("0.00"))
        self.assertEqual(result["sgst_amount"], Decimal("0.00"))
        self.assertEqual(result["total_gst"], Decimal("0.00"))
        self.assertEqual(result["total_tax"], Decimal("0.00"))
        self.assertEqual(result["gst_rate"], Decimal("0.00"))

    def test_taxability_nil_rated(self):
        line = self._create_line(self.invoice_intra, taxability_type_snapshot=TaxabilityType.NIL_RATED, gst_rate_snapshot=Decimal('0.00'))
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        self.assertEqual(result["taxability_type"], TaxabilityType.NIL_RATED)
        self.assertEqual(result["total_tax"], Decimal("0.00"))

    def test_taxability_non_gst(self):
        line = self._create_line(self.invoice_intra, taxability_type_snapshot=TaxabilityType.NON_GST, gst_rate_snapshot=Decimal('0.00'))
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        self.assertEqual(result["taxability_type"], TaxabilityType.NON_GST)
        self.assertEqual(result["total_tax"], Decimal("0.00"))

    def test_missing_pos_raises_error(self):
        line = self._create_line(self.invoice_intra)
        with self.assertRaises(ValidationError):
            calculate_line_tax(line, self.org.state_code, "")

    def test_inclusive_pricing(self):
        # 1180 inclusive at 18% GST -> 1000 taxable base
        line = self._create_line(
            self.invoice_intra, 
            quantity=1, 
            unit_price=Decimal('1180.00'),
            price_basis_snapshot=PriceBasis.INCLUSIVE,
            gst_rate_snapshot=Decimal('18.00')
        )
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        self.assertEqual(result["taxable_value"], Decimal("1000.00"))
        self.assertEqual(result["cgst_amount"], Decimal("90.00"))
        self.assertEqual(result["sgst_amount"], Decimal("90.00"))
        self.assertEqual(result["total_gst"], Decimal("180.00"))

    def test_inclusive_pricing_0_percent(self):
        # 1180 inclusive at 0% GST -> 1180 taxable base
        line = self._create_line(
            self.invoice_intra, 
            quantity=1, 
            unit_price=Decimal('1180.00'),
            price_basis_snapshot=PriceBasis.INCLUSIVE,
            taxability_type_snapshot=TaxabilityType.EXEMPT,
            gst_rate_snapshot=Decimal('0.00')
        )
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        self.assertEqual(result["taxable_value"], Decimal("1180.00"))
        self.assertEqual(result["cgst_amount"], Decimal("0.00"))
        self.assertEqual(result["total_gst"], Decimal("0.00"))

    def test_discount_affects_gst_base(self):
        # Qty 2, Unit Price 1000 -> Gross 2000
        # Discount 10% -> Discount Amount 200
        # Net transaction value -> 1800
        line = self._create_line(
            self.invoice_intra,
            discount_type=DiscountType.PERCENTAGE,
            discount_value=Decimal("10.00")
        )
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        self.assertEqual(result["taxable_value"], Decimal("1800.00"))
        self.assertEqual(result["cgst_amount"], Decimal("162.00")) # 9% of 1800
        self.assertEqual(result["sgst_amount"], Decimal("162.00"))
        self.assertEqual(result["total_tax"], Decimal("324.00"))

    def test_cess_percentage(self):
        line = self._create_line(
            self.invoice_intra,
            cess_applicable_snapshot=True,
            cess_type_snapshot=CessType.PERCENTAGE,
            cess_rate_snapshot=Decimal("12.00") # 12%
        )
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        self.assertEqual(result["taxable_value"], Decimal("2000.00"))
        self.assertEqual(result["total_gst"], Decimal("360.00"))
        self.assertEqual(result["cess_amount"], Decimal("240.00")) # 12% of 2000
        self.assertEqual(result["total_tax"], Decimal("600.00")) # 360 + 240

    def test_cess_fixed_amount(self):
        line = self._create_line(
            self.invoice_intra,
            quantity=3,
            cess_applicable_snapshot=True,
            cess_type_snapshot=CessType.FIXED_AMOUNT,
            cess_rate_snapshot=Decimal("400.00") # 400 per unit
        )
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        # GST is 18% of 3000 = 540
        self.assertEqual(result["taxable_value"], Decimal("3000.00"))
        self.assertEqual(result["total_gst"], Decimal("540.00"))
        self.assertEqual(result["cess_amount"], Decimal("1200.00")) # 400 * 3
        self.assertEqual(result["total_tax"], Decimal("1740.00"))

    def test_rcm_preserved(self):
        line = self._create_line(
            self.invoice_intra,
            reverse_charge_snapshot=True
        )
        result = calculate_line_tax(line, self.org.state_code, self.invoice_intra.place_of_supply)
        
        self.assertEqual(result["reverse_charge"], True)

    def test_invoice_aggregation(self):
        # Add multiple lines to invoice_intra
        # Line 1: Taxable 18% (1000 * 2 = 2000 -> CGST 180, SGST 180)
        self._create_line(self.invoice_intra)
        
        # Line 2: Exempt (500 * 1 = 500)
        self._create_line(
            self.invoice_intra, 
            quantity=1, 
            unit_price=Decimal("500.00"), 
            taxability_type_snapshot=TaxabilityType.EXEMPT,
            gst_rate_snapshot=Decimal('0.00')
        )
        
        # Line 3: Taxable 12% with 10% cess (100 * 10 = 1000 -> CGST 60, SGST 60, Cess 100)
        self._create_line(
            self.invoice_intra,
            quantity=10,
            unit_price=Decimal("100.00"),
            gst_rate_snapshot=Decimal("12.00"),
            cess_applicable_snapshot=True,
            cess_type_snapshot=CessType.PERCENTAGE,
            cess_rate_snapshot=Decimal("10.00")
        )
        
        result = aggregate_invoice_taxes(self.invoice_intra, self.org.state_code)
        
        self.assertEqual(result["total_taxable_value"], Decimal("3500.00")) # 2000 + 500 + 1000
        self.assertEqual(result["total_cgst"], Decimal("240.00")) # 180 + 60
        self.assertEqual(result["total_sgst"], Decimal("240.00"))
        self.assertEqual(result["total_igst"], Decimal("0.00"))
        self.assertEqual(result["total_gst"], Decimal("480.00"))
        self.assertEqual(result["total_cess"], Decimal("100.00"))
        self.assertEqual(result["total_tax"], Decimal("580.00")) # 480 + 100
