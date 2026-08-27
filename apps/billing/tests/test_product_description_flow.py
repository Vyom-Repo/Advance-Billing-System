"""
apps/billing/tests/test_product_description_flow.py

Comprehensive tests for optional, editable, multi-line product descriptions:
1. Product creation with multi-line description.
2. Invoice creation automatically populating description into InvoiceLine.
3. Modifying invoice line description per-invoice without overwriting master Product description.
4. Preserving line breaks in pdf_adapter and bill_serializer output.
5. Invoices & products without descriptions working normally (backward compatibility).
"""

from decimal import Decimal
import datetime
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.organization.models import Organization
from apps.customers.models import Customer
from apps.products.models import Product, ProductType, TaxabilityType
from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus
from apps.billing.services.lifecycle import populate_line_snapshot, prepare_invoice_snapshots
from apps.billing.services.pdf_adapter import invoice_to_pdf_dicts
from apps.invoices.services.bill_serializer import serialize_bill_for_render

User = get_user_model()


class ProductDescriptionFlowTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="desc_user",
            email="desc@example.com",
            password="Password123!",
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Description Test Corp",
            legal_business_name="Description Test Corp Pvt Ltd",
            business_email="desc@example.com",
            address_line_1="100 Innovation Way",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            country="India",
            gstin="27AAAAA0000A1Z5",
            state_code="27",
        )
        self.customer = Customer.objects.create(
            organization=self.org,
            name="Acme Clients Ltd",
            billing_address_line_1="200 Corporate Blvd",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_pin_code="400002",
            billing_state_code="27",
            gstin="27BBBBA1111B1Z2",
        )
        self.client = Client()
        self.client.login(username="desc_user", password="Password123!")

    def test_product_master_creation_with_multiline_description(self):
        multiline_desc = "Feature A: Enterprise Security\nFeature B: 24/7 Support\nFeature C: Dedicated SLA"
        product = Product.objects.create(
            organization=self.org,
            name="Enterprise Software Suite",
            description=multiline_desc,
            product_type=ProductType.GOODS,
            hsn_code="852380",
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            unit_price=Decimal("50000.00"),
            uqc="NOS",
        )
        self.assertEqual(product.description, multiline_desc)
        self.assertIn("Feature B: 24/7 Support", product.as_invoice_snapshot()["description"])

    def test_invoice_line_auto_populates_description_from_product(self):
        desc = "Standard Maintenance Package\nIncludes quarterly audits"
        product = Product.objects.create(
            organization=self.org,
            name="Maintenance Service",
            description=desc,
            product_type=ProductType.SERVICE,
            sac_code="998313",
            unit_price=Decimal("12000.00"),
            uqc="OTH",
        )

        invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=datetime.date.today(),
            place_of_supply="27",
            status=InvoiceStatus.DRAFT,
        )

        line = InvoiceLine(
            invoice=invoice,
            product=product,
            position=1,
            quantity=Decimal("1.000"),
            unit_price=Decimal("12000.00"),
        )
        populate_line_snapshot(line)
        line.save()

        self.assertEqual(line.description, desc)
        self.assertEqual(line.product_name_snapshot, "Maintenance Service")

    def test_editing_invoice_line_description_does_not_mutate_master_product(self):
        master_desc = "Master Product Description Original"
        product = Product.objects.create(
            organization=self.org,
            name="Customizable Widget",
            description=master_desc,
            product_type=ProductType.GOODS,
            hsn_code="852380",
            unit_price=Decimal("1000.00"),
            uqc="NOS",
        )

        invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=datetime.date.today(),
            place_of_supply="27",
            status=InvoiceStatus.DRAFT,
        )

        invoice_specific_desc = "Special customized build for Acme Invoice #101\nIncludes custom engraving"
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product=product,
            position=1,
            product_name_snapshot=product.name,
            description=invoice_specific_desc,
            quantity=Decimal("2.000"),
            unit_price=Decimal("1000.00"),
            taxable_value=Decimal("2000.00"),
            line_total=Decimal("2360.00"),
            gst_rate_snapshot=Decimal("18.00"),
            hsn_sac_snapshot="852380",
            taxability_type_snapshot="taxable",
            price_basis_snapshot="exclusive",
            uqc_snapshot="NOS",
        )

        # Master product description must remain unchanged
        product.refresh_from_db()
        self.assertEqual(product.description, master_desc)

        # Line description is customized for this invoice
        line.refresh_from_db()
        self.assertEqual(line.description, invoice_specific_desc)

    def test_pdf_adapter_and_serializer_preserve_multiline_description(self):
        multiline_desc = "Line 1: High performance Server\nLine 2: 64GB RAM / 2TB SSD\nLine 3: 3-Year Warranty"
        product = Product.objects.create(
            organization=self.org,
            name="Rack Server X",
            description=multiline_desc,
            product_type=ProductType.GOODS,
            hsn_code="847130",
            unit_price=Decimal("150000.00"),
            uqc="NOS",
        )

        invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=datetime.date.today(),
            place_of_supply="27",
            status=InvoiceStatus.DRAFT,
            subtotal=Decimal("150000.00"),
            taxable_amount=Decimal("150000.00"),
            cgst_total=Decimal("13500.00"),
            sgst_total=Decimal("13500.00"),
            grand_total=Decimal("177000.00"),
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product=product,
            position=1,
            product_name_snapshot=product.name,
            description=multiline_desc,
            quantity=Decimal("1.000"),
            unit_price=Decimal("150000.00"),
            taxable_value=Decimal("150000.00"),
            cgst_amount=Decimal("13500.00"),
            sgst_amount=Decimal("13500.00"),
            line_total=Decimal("177000.00"),
            gst_rate_snapshot=Decimal("18.00"),
            hsn_sac_snapshot="847130",
            taxability_type_snapshot="taxable",
            price_basis_snapshot="exclusive",
            uqc_snapshot="NOS",
        )

        # Test pdf_adapter
        inv_dict, cust_dict, items_list, comp_dict = invoice_to_pdf_dicts(invoice)
        self.assertEqual(len(items_list), 1)
        self.assertEqual(items_list[0]["description"], multiline_desc)

        # Test canonical bill serializer
        serialized = serialize_bill_for_render(inv_dict, cust_dict, items_list, comp_dict, org=self.org)
        serialized_items = serialized["items"]
        self.assertEqual(len(serialized_items), 1)
        self.assertEqual(serialized_items[0]["description"], multiline_desc)

    def test_backward_compatibility_without_description(self):
        product = Product.objects.create(
            organization=self.org,
            name="Simple Product",
            description="",
            product_type=ProductType.GOODS,
            hsn_code="123456",
            unit_price=Decimal("100.00"),
            uqc="NOS",
        )
        invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=datetime.date.today(),
            place_of_supply="27",
            status=InvoiceStatus.DRAFT,
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            product=product,
            position=1,
            product_name_snapshot=product.name,
            description="",
            quantity=Decimal("1.000"),
            unit_price=Decimal("100.00"),
            taxable_value=Decimal("100.00"),
            line_total=Decimal("118.00"),
            gst_rate_snapshot=Decimal("18.00"),
            hsn_sac_snapshot="123456",
            taxability_type_snapshot="taxable",
            price_basis_snapshot="exclusive",
            uqc_snapshot="NOS",
        )

        inv_dict, cust_dict, items_list, comp_dict = invoice_to_pdf_dicts(invoice)
        serialized = serialize_bill_for_render(inv_dict, cust_dict, items_list, comp_dict, org=self.org)
        self.assertEqual(serialized["items"][0]["description"], "")
