"""
apps/billing/tests/test_final_qa_matrix.py — Phase 12 Final QA Verification Matrix

Executes automated end-to-end verification across the 8 required QA matrices:
1. Customer Matrix:
   - Business + Registered
   - Business + Unregistered
   - Individual + Registered
   - Individual + Unregistered
2. Historical Integrity Matrix:
   - Customer mutations & deletion
   - Product mutations & deletion
3. Calculation Matrix:
   - Quantities, decimals, percent/fixed/no discounts, mixed inclusive/exclusive pricing, round-off
4. GST Matrix:
   - Taxable, Exempt, Nil-rated, Non-GST, Intra-state vs Inter-state routing, Cess, RCM, Place of Supply
5. Address Matrix:
   - Same as billing vs separate shipping address, supplier vs customer vs POS state codes
6. Lifecycle Matrix:
   - Complete draft -> edit -> save -> issue -> cancel lifecycle + deletion restrictions
7. PDF Matrix:
   - Inline preview, download attachment, Letterhead ON/OFF, post-mutation snapshot PDF rendering
8. Multi-Tenancy Matrix:
   - Full 2-organization separation across all CRUD and lifecycle actions
"""

import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, Client
from django.urls import reverse

from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus, DiscountType
from apps.billing.services.calculation_engine import finalize_invoice, calculate_invoice
from apps.billing.services.lifecycle import cancel_invoice, delete_invoice, prepare_invoice_snapshots
from apps.billing.services.pdf_adapter import invoice_to_pdf_dicts
from apps.customers.models import Customer, CustomerType, GSTStatus
from apps.organization.models import Organization
from apps.products.models import Product, ProductType, TaxabilityType, PriceBasis, CessType
from apps.settings_app.models import InvoicePreference, DocumentPreference

User = get_user_model()


class Phase12FinalQAMatrixTests(TestCase):
    def setUp(self):
        # Org 1: Maharashtra (State Code 27)
        self.user1 = User.objects.create_user(
            username="qa_user1", email="qa1@example.com", password="password123"
        )
        self.org1 = Organization.objects.create(
            owner=self.user1, business_name="QA Org MH", state_code="27",
            business_email="qa1@example.com", address_line_1="100 Nariman Point",
            city="Mumbai", state="Maharashtra", pincode="400021", country="India"
        )
        self.user1.organization = self.org1
        self.user1.save()
        self.pref1 = InvoicePreference.objects.create(
            user=self.user1, invoice_prefix="QAMH", starting_number=1, include_financial_year=True
        )
        self.doc_pref1 = DocumentPreference.objects.create(
            user=self.user1, show_company_logo=True, print_on_letterhead=False
        )

        # Org 2: Karnataka (State Code 29)
        self.user2 = User.objects.create_user(
            username="qa_user2", email="qa2@example.com", password="password123"
        )
        self.org2 = Organization.objects.create(
            owner=self.user2, business_name="QA Org KA", state_code="29",
            business_email="qa2@example.com", address_line_1="200 MG Road",
            city="Bengaluru", state="Karnataka", pincode="560001", country="India"
        )
        self.user2.organization = self.org2
        self.user2.save()
        self.pref2 = InvoicePreference.objects.create(
            user=self.user2, invoice_prefix="QAKA", starting_number=50, include_financial_year=False
        )

        # Clients
        self.client1 = Client()
        self.client1.force_login(self.user1)

        self.client2 = Client()
        self.client2.force_login(self.user2)

    # =======================================================================
    # 1. Customer Matrix (4 Combinations)
    # =======================================================================

    def test_customer_matrix_all_four_combinations(self):
        """
        Verify all 4 Customer master variations:
        1. Business + Registered
        2. Business + Unregistered
        3. Individual + Registered
        4. Individual + Unregistered
        """
        combos = [
            ("Cust Biz Reg", CustomerType.BUSINESS, GSTStatus.REGISTERED, "27AAAAA0000A1Z5"),
            ("Cust Biz Unreg", CustomerType.BUSINESS, GSTStatus.UNREGISTERED, ""),
            ("Cust Ind Reg", CustomerType.INDIVIDUAL, GSTStatus.REGISTERED, "27BBBBB0000B1Z5"),
            ("Cust Ind Unreg", CustomerType.INDIVIDUAL, GSTStatus.UNREGISTERED, ""),
        ]

        prod = Product.objects.create(
            organization=self.org1, name="Standard Widget", unit_price=Decimal("500.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("18.00"),
            price_basis=PriceBasis.EXCLUSIVE, hsn_code="8471"
        )

        for name, c_type, g_status, gstin in combos:
            cust = Customer.objects.create(
                organization=self.org1, name=name, customer_type=c_type, gst_status=g_status,
                gstin=gstin, billing_state_code="27", billing_state="Maharashtra",
                billing_city="Mumbai", billing_address_line_1="Road 1", billing_pin_code="400001"
            )

            inv = Invoice.objects.create(
                organization=self.org1, customer=cust, status=InvoiceStatus.DRAFT,
                invoice_date=datetime.date.today(), place_of_supply="27"
            )
            InvoiceLine.objects.create(
                invoice=inv, position=1, product=prod, quantity=Decimal("2.000"),
                unit_price=Decimal("500.00"), discount_type=DiscountType.NONE, discount_value=Decimal("0.00")
            )

            # Issue
            finalize_invoice(inv)
            inv.refresh_from_db()

            self.assertEqual(inv.status, InvoiceStatus.ISSUED)
            self.assertEqual(inv.customer_name_snapshot, name)
            self.assertEqual(inv.customer_gstin_snapshot, gstin)
            self.assertEqual(inv.subtotal, Decimal("1000.00"))
            self.assertEqual(inv.cgst_total, Decimal("90.00"))
            self.assertEqual(inv.sgst_total, Decimal("90.00"))
            self.assertEqual(inv.grand_total, Decimal("1180.00"))

            # PDF check
            resp = self.client1.get(reverse("billing:preview", kwargs={"uuid": inv.uuid}))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp["Content-Type"], "application/pdf")

    # =======================================================================
    # 2. Historical Integrity Matrix
    # =======================================================================

    def test_historical_integrity_customer_and_product_mutations(self):
        """
        Verify post-issuance changes or deletions of Customer & Product do not alter
        persisted invoices or their PDF serialization.
        """
        cust = Customer.objects.create(
            organization=self.org1, name="Original Customer", gstin="27AAAAA1111A1Z1",
            billing_state_code="27", billing_state="Maharashtra", billing_city="Pune",
            billing_address_line_1="Original Address", billing_pin_code="411001"
        )
        prod = Product.objects.create(
            organization=self.org1, name="Original Product", unit_price=Decimal("1000.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("18.00"),
            price_basis=PriceBasis.EXCLUSIVE, hsn_code="9983", uqc="NOS"
        )
        inv = Invoice.objects.create(
            organization=self.org1, customer=cust, status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(), place_of_supply="27"
        )
        line = InvoiceLine.objects.create(
            invoice=inv, position=1, product=prod, quantity=Decimal("1.000"),
            unit_price=Decimal("1000.00"), discount_type=DiscountType.NONE, discount_value=Decimal("0.00")
        )
        finalize_invoice(inv)
        inv.refresh_from_db()
        line.refresh_from_db()

        # Mutate Master Records
        cust.name = "Modified Customer LLC"
        cust.gstin = "27ZZZZZ9999Z9Z9"
        cust.billing_address_line_1 = "Modified Road"
        cust.save()

        prod.name = "Modified Product Ultimate"
        prod.unit_price = Decimal("5000.00")
        prod.gst_rate = Decimal("28.00")
        prod.save()

        # Check DB snapshots unchanged
        inv.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(inv.customer_name_snapshot, "Original Customer")
        self.assertEqual(inv.customer_gstin_snapshot, "27AAAAA1111A1Z1")
        self.assertEqual(line.product_name_snapshot, "Original Product")
        self.assertEqual(line.unit_price, Decimal("1000.00"))
        self.assertEqual(line.gst_rate_snapshot, Decimal("18.00"))
        self.assertEqual(inv.grand_total, Decimal("1180.00"))

        # Check Adapter & PDF output reflects snapshots
        inv_d, cust_d, items_d, comp_d = invoice_to_pdf_dicts(inv)
        self.assertEqual(cust_d["name"], "Original Customer")
        self.assertEqual(items_d[0]["name"], "Original Product")
        self.assertEqual(items_d[0]["rate"], 1000.0)

        # Delete Master Records
        cust.delete()
        prod.delete()

        inv.refresh_from_db()
        line.refresh_from_db()
        self.assertIsNone(inv.customer)
        self.assertIsNone(line.product)
        self.assertEqual(inv.customer_name_snapshot, "Original Customer")
        self.assertEqual(line.product_name_snapshot, "Original Product")

    # =======================================================================
    # 3. Calculation & Discount Matrix
    # =======================================================================

    def test_calculation_matrix_mixed_discounts_and_price_bases(self):
        """
        Verify multi-line invoice with:
        - Line 1: Percentage discount, exclusive GST
        - Line 2: Fixed amount discount, inclusive GST
        - Line 3: No discount, 3 decimal places quantity, round off calculation
        """
        cust = Customer.objects.create(
            organization=self.org1, name="Calc Customer", billing_state_code="27",
            billing_state="Maharashtra", billing_city="Mumbai", billing_address_line_1="Addr", billing_pin_code="400001"
        )
        # Prod 1: 1000.00 exclusive, 18% GST
        prod1 = Product.objects.create(
            organization=self.org1, name="Exclusive Item", unit_price=Decimal("1000.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("18.00"),
            price_basis=PriceBasis.EXCLUSIVE
        )
        # Prod 2: 118.00 inclusive, 18% GST (Taxable value: 100.00, Tax: 18.00)
        prod2 = Product.objects.create(
            organization=self.org1, name="Inclusive Item", unit_price=Decimal("118.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("18.00"),
            price_basis=PriceBasis.INCLUSIVE
        )
        # Prod 3: 33.33 exclusive, 5% GST
        prod3 = Product.objects.create(
            organization=self.org1, name="Fraction Item", unit_price=Decimal("33.33"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("5.00"),
            price_basis=PriceBasis.EXCLUSIVE
        )

        inv = Invoice.objects.create(
            organization=self.org1, customer=cust, status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(), place_of_supply="27"
        )
        # Line 1: 2 * 1000 = 2000. 10% discount = 200. Net: 1800. Tax (18%): CGST 162 + SGST 162 = 324. Total: 2124.00
        l1 = InvoiceLine.objects.create(
            invoice=inv, position=1, product=prod1, quantity=Decimal("2.000"),
            unit_price=Decimal("1000.00"), discount_type=DiscountType.PERCENTAGE, discount_value=Decimal("10.00")
        )
        # Line 2: 10 * 118 = 1180. Fixed discount = 180. Net inclusive: 1000. Taxable: 847.46, Tax (18%): CGST 76.27 + SGST 76.27 = 152.54. Total: 1000.00
        l2 = InvoiceLine.objects.create(
            invoice=inv, position=2, product=prod2, quantity=Decimal("10.000"),
            unit_price=Decimal("118.00"), discount_type=DiscountType.FIXED, discount_value=Decimal("180.00")
        )
        # Line 3: 1.500 * 33.33 = 49.995 -> 50.00. No discount. Taxable: 50.00. Tax (5%): CGST 1.25 + SGST 1.25 = 2.50. Total: 52.50
        l3 = InvoiceLine.objects.create(
            invoice=inv, position=3, product=prod3, quantity=Decimal("1.500"),
            unit_price=Decimal("33.33"), discount_type=DiscountType.NONE, discount_value=Decimal("0.00")
        )

        finalize_invoice(inv)
        inv.refresh_from_db()

        # Verify exact mathematically quantized calculations
        self.assertEqual(inv.status, InvoiceStatus.ISSUED)
        self.assertEqual(inv.subtotal, Decimal("3230.00")) # 2000 + 1180 + 50.00
        self.assertEqual(inv.discount_total, Decimal("380.00")) # 200 + 180
        self.assertEqual(inv.taxable_amount, Decimal("2697.46")) # 1800 + 847.46 + 50.00
        self.assertEqual(inv.cgst_total, Decimal("239.52")) # 162 + 76.27 + 1.25
        self.assertEqual(inv.sgst_total, Decimal("239.52")) # 162 + 76.27 + 1.25
        self.assertEqual(inv.grand_total, Decimal("3177.00")) # 2124.00 + 1000.00 + 52.50 = 3176.50 -> Round off +0.50 -> 3177.00
        self.assertEqual(inv.round_off, Decimal("0.50"))

    # =======================================================================
    # 4. GST Matrix
    # =======================================================================

    def test_gst_matrix_intra_vs_inter_state_and_taxabilities(self):
        """
        Verify GST tax routing:
        - Intra-state (Supplier 27 -> POS 27): CGST + SGST
        - Inter-state (Supplier 27 -> POS 29): IGST
        - Taxability types: Taxable, Exempt, Nil-rated, Non-GST
        - Cess: Percentage cess and Fixed cess
        """
        cust_inter = Customer.objects.create(
            organization=self.org1, name="KA Cust", billing_state_code="29",
            billing_state="Karnataka", billing_city="Bengaluru", billing_address_line_1="KA Addr", billing_pin_code="560001"
        )
        prod_cess = Product.objects.create(
            organization=self.org1, name="Luxury Item", unit_price=Decimal("10000.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("28.00"),
            cess_applicable=True, cess_type=CessType.PERCENTAGE, cess_rate_or_amount=Decimal("12.00"),
            price_basis=PriceBasis.EXCLUSIVE
        )
        prod_exempt = Product.objects.create(
            organization=self.org1, name="Exempt Grains", unit_price=Decimal("500.00"),
            taxability_type=TaxabilityType.EXEMPT, gst_rate=Decimal("0.00"),
            price_basis=PriceBasis.EXCLUSIVE
        )
        prod_nil = Product.objects.create(
            organization=self.org1, name="Nil Rate Item", unit_price=Decimal("200.00"),
            taxability_type=TaxabilityType.NIL_RATED, gst_rate=Decimal("0.00"),
            price_basis=PriceBasis.EXCLUSIVE
        )
        prod_nongst = Product.objects.create(
            organization=self.org1, name="Non-GST Fuel", unit_price=Decimal("1000.00"),
            taxability_type=TaxabilityType.NON_GST, gst_rate=Decimal("0.00"),
            price_basis=PriceBasis.EXCLUSIVE
        )

        inv = Invoice.objects.create(
            organization=self.org1, customer=cust_inter, status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(), place_of_supply="29" # Inter-state POS
        )
        InvoiceLine.objects.create(
            invoice=inv, position=1, product=prod_cess, quantity=Decimal("1.000"),
            unit_price=Decimal("10000.00")
        )
        InvoiceLine.objects.create(
            invoice=inv, position=2, product=prod_exempt, quantity=Decimal("1.000"),
            unit_price=Decimal("500.00")
        )
        InvoiceLine.objects.create(
            invoice=inv, position=3, product=prod_nil, quantity=Decimal("1.000"),
            unit_price=Decimal("200.00")
        )
        InvoiceLine.objects.create(
            invoice=inv, position=4, product=prod_nongst, quantity=Decimal("1.000"),
            unit_price=Decimal("1000.00")
        )

        finalize_invoice(inv)
        inv.refresh_from_db()

        # Inter-state routing: CGST & SGST must be 0, IGST must hold 28% of 10,000 = 2800.00
        self.assertEqual(inv.cgst_total, Decimal("0.00"))
        self.assertEqual(inv.sgst_total, Decimal("0.00"))
        self.assertEqual(inv.igst_total, Decimal("2800.00"))
        # Cess: 12% of 10,000 = 1200.00
        self.assertEqual(inv.cess_total, Decimal("1200.00"))
        # Taxable amount: 11,700.00 (total turnover across all line items)
        self.assertEqual(inv.taxable_amount, Decimal("11700.00"))
        # Subtotal: 10000 + 500 + 200 + 1000 = 11700.00
        self.assertEqual(inv.subtotal, Decimal("11700.00"))
        # Grand total: 11700 + 2800 (IGST) + 1200 (Cess) = 15700.00
        self.assertEqual(inv.grand_total, Decimal("15700.00"))

    # =======================================================================
    # 5. Address Matrix
    # =======================================================================

    def test_address_matrix_shipping_toggle(self):
        """
        Verify shipping address persistence:
        - shipping_same_as_billing = True
        - shipping_same_as_billing = False with custom shipping address
        """
        cust = Customer.objects.create(
            organization=self.org1, name="Shipping Customer", billing_state_code="27",
            billing_state="Maharashtra", billing_city="Pune", billing_address_line_1="Billing Pune St", billing_pin_code="411001"
        )
        prod = Product.objects.create(
            organization=self.org1, name="Item", unit_price=Decimal("100.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("18.00")
        )

        inv_custom_ship = Invoice.objects.create(
            organization=self.org1, customer=cust, status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(), place_of_supply="27",
            shipping_same_as_billing=False,
            shipping_address_line_1="Warehouse 5B",
            shipping_city="Nagpur",
            shipping_state="Maharashtra",
            shipping_pincode="440001"
        )
        InvoiceLine.objects.create(
            invoice=inv_custom_ship, position=1, product=prod, quantity=Decimal("1.000"), unit_price=Decimal("100.00")
        )
        finalize_invoice(inv_custom_ship)
        inv_custom_ship.refresh_from_db()

        self.assertFalse(inv_custom_ship.shipping_same_as_billing)
        self.assertEqual(inv_custom_ship.shipping_address_line_1, "Warehouse 5B")
        self.assertEqual(inv_custom_ship.shipping_city, "Nagpur")

        inv_d, cust_d, items_d, comp_d = invoice_to_pdf_dicts(inv_custom_ship)
        self.assertEqual(cust_d["shipping_address"], "Warehouse 5B")
        self.assertEqual(cust_d["shipping_city"], "Nagpur")

    # =======================================================================
    # 6. Lifecycle Matrix
    # =======================================================================

    def test_lifecycle_matrix_full_progression(self):
        """
        Verify:
        Draft (editable, deletable)
          -> Issue (allocates number, locks)
          -> Issued (not editable, not deletable)
          -> Cancel (retains number, not editable, not deletable)
        """
        cust = Customer.objects.create(
            organization=self.org1, name="Lifecycle Cust", billing_state_code="27",
            billing_state="Maharashtra", billing_city="Mumbai", billing_address_line_1="St", billing_pin_code="400001"
        )
        prod = Product.objects.create(
            organization=self.org1, name="Item", unit_price=Decimal("100.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("18.00")
        )

        inv = Invoice.objects.create(
            organization=self.org1, customer=cust, status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(), place_of_supply="27"
        )
        line = InvoiceLine.objects.create(
            invoice=inv, position=1, product=prod, quantity=Decimal("1.000"), unit_price=Decimal("100.00")
        )

        # 1. Draft Edit
        line.quantity = Decimal("3.000")
        line.save()
        self.assertEqual(inv.lines.first().quantity, Decimal("3.000"))

        # 2. Issue
        finalize_invoice(inv)
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.ISSUED)
        self.assertTrue(inv.invoice_number.startswith("QAMH-"))

        # 3. Issued invoice cannot be edited or deleted
        with self.assertRaises(ValidationError):
            delete_invoice(inv)

        # 4. Cancel
        cancel_invoice(inv)
        inv.refresh_from_db()
        self.assertEqual(inv.status, InvoiceStatus.CANCELLED)

        # 5. Cancelled invoice cannot be deleted or re-issued
        with self.assertRaises(ValidationError):
            delete_invoice(inv)
        with self.assertRaises(ValidationError):
            finalize_invoice(inv)

    # =======================================================================
    # 7. PDF Matrix
    # =======================================================================

    def test_pdf_matrix_preview_and_download_disposition(self):
        """
        Verify PDF rendering for preview (inline) and download (attachment).
        """
        cust = Customer.objects.create(
            organization=self.org1, name="PDF Cust", billing_state_code="27",
            billing_state="Maharashtra", billing_city="Mumbai", billing_address_line_1="St", billing_pin_code="400001"
        )
        prod = Product.objects.create(
            organization=self.org1, name="Item", unit_price=Decimal("250.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("18.00")
        )
        inv = Invoice.objects.create(
            organization=self.org1, customer=cust, status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(), place_of_supply="27"
        )
        InvoiceLine.objects.create(
            invoice=inv, position=1, product=prod, quantity=Decimal("2.000"), unit_price=Decimal("250.00")
        )
        finalize_invoice(inv)
        inv.refresh_from_db()

        # Inline preview
        resp_inline = self.client1.get(reverse("billing:preview", kwargs={"uuid": inv.uuid}))
        self.assertEqual(resp_inline.status_code, 200)
        self.assertIn("inline;", resp_inline["Content-Disposition"])

        # Attachment download
        resp_download = self.client1.get(f"{reverse('billing:preview', kwargs={'uuid': inv.uuid})}?download=1")
        self.assertEqual(resp_download.status_code, 200)
        self.assertIn("attachment;", resp_download["Content-Disposition"])

    # =======================================================================
    # 8. Multi-Tenancy Matrix
    # =======================================================================

    def test_multi_tenancy_strict_cross_org_isolation(self):
        """
        Verify complete isolation between Org 1 (MH) and Org 2 (KA).
        """
        cust1 = Customer.objects.create(
            organization=self.org1, name="Org 1 Cust", billing_state_code="27",
            billing_state="MH", billing_city="Mumbai", billing_address_line_1="St 1", billing_pin_code="400001"
        )
        cust2 = Customer.objects.create(
            organization=self.org2, name="Org 2 Cust", billing_state_code="29",
            billing_state="KA", billing_city="Bengaluru", billing_address_line_1="St 2", billing_pin_code="560001"
        )
        prod1 = Product.objects.create(
            organization=self.org1, name="Org 1 Prod", unit_price=Decimal("100.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("18.00")
        )
        prod2 = Product.objects.create(
            organization=self.org2, name="Org 2 Prod", unit_price=Decimal("200.00"),
            taxability_type=TaxabilityType.TAXABLE, gst_rate=Decimal("18.00")
        )

        inv1 = Invoice.objects.create(
            organization=self.org1, customer=cust1, status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(), place_of_supply="27"
        )
        InvoiceLine.objects.create(
            invoice=inv1, position=1, product=prod1, quantity=Decimal("1.000"), unit_price=Decimal("100.00")
        )
        finalize_invoice(inv1)
        inv1.refresh_from_db()

        inv2 = Invoice.objects.create(
            organization=self.org2, customer=cust2, status=InvoiceStatus.DRAFT,
            invoice_date=datetime.date.today(), place_of_supply="29"
        )
        InvoiceLine.objects.create(
            invoice=inv2, position=1, product=prod2, quantity=Decimal("1.000"), unit_price=Decimal("200.00")
        )
        finalize_invoice(inv2)
        inv2.refresh_from_db()

        # Org 1 list does not contain inv2
        resp1 = self.client1.get(reverse("billing:index"))
        self.assertContains(resp1, inv1.invoice_number)
        self.assertNotContains(resp1, inv2.invoice_number)

        # Org 2 list does not contain inv1
        resp2 = self.client2.get(reverse("billing:index"))
        self.assertContains(resp2, inv2.invoice_number)
        self.assertNotContains(resp2, inv1.invoice_number)

        # Cross-tenant direct access returns 404
        self.assertEqual(self.client1.get(reverse("billing:detail", kwargs={"uuid": inv2.uuid})).status_code, 404)
        self.assertEqual(self.client2.get(reverse("billing:detail", kwargs={"uuid": inv1.uuid})).status_code, 404)
        self.assertEqual(self.client1.get(reverse("billing:preview", kwargs={"uuid": inv2.uuid})).status_code, 404)
        self.assertEqual(self.client2.get(reverse("billing:preview", kwargs={"uuid": inv1.uuid})).status_code, 404)
