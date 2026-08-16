import json
from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus, DiscountType
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product, TaxabilityType
from apps.settings_app.models import DocumentPreference
from apps.billing.services.pdf_adapter import invoice_to_pdf_dicts

User = get_user_model()


class Phase10PDFIntegrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="test_pdf_user",
            email="test_pdf@example.com", 
            password="password123"
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Test PDF Org",
            state_code="MH",
            business_email="test@pdforg.com"
        )
        self.user.organization = self.org
        self.user.save()

        # Document Preferences
        DocumentPreference.objects.create(
            user=self.user,
            show_company_logo=True,
            show_company_header=True,
            print_on_letterhead=False
        )

        self.customer = Customer.objects.create(
            organization=self.org,
            name="Alpha Corp",
            billing_state_code="MH",
            billing_address_line_1="123 Alpha St",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_pin_code="400001"
        )
        
        self.product = Product.objects.create(
            organization=self.org,
            name="Consulting Services",
            unit_price=Decimal("1000.00"),
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            hsn_code="9983"
        )

        # Create an Issued Invoice manually mirroring Phase 08 logic
        self.invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-001",
            invoice_date="2026-08-15",
            place_of_supply="MH",
            
            customer_name_snapshot=self.customer.name,
            customer_billing_address_snapshot=self.customer.full_billing_address,
            customer_state_code_snapshot=self.customer.billing_state_code,
            
            subtotal=Decimal("1000.00"),
            taxable_amount=Decimal("1000.00"),
            cgst_total=Decimal("90.00"),
            sgst_total=Decimal("90.00"),
            grand_total=Decimal("1180.00"),
        )
        
        self.line = InvoiceLine.objects.create(
            invoice=self.invoice,
            position=1,
            product=self.product,
            product_name_snapshot=self.product.name,
            hsn_sac_snapshot=self.product.hsn_code,
            uqc_snapshot="NOS",
            gst_rate_snapshot=self.product.gst_rate,
            
            quantity=Decimal("1.000"),
            unit_price=Decimal("1000.00"),
            taxable_value=Decimal("1000.00"),
            cgst_amount=Decimal("90.00"),
            sgst_amount=Decimal("90.00"),
            line_total=Decimal("1180.00")
        )

    def test_pdf_adapter_mapping(self):
        """
        Prove the adapter accurately maps ORM to bill_data dicts
        and does not recalculate anything.
        """
        invoice_dict, customer_dict, items_list, company_dict = invoice_to_pdf_dicts(self.invoice)
        
        # 1. Invoice mapping
        self.assertEqual(invoice_dict["number"], "INV-001")
        self.assertEqual(invoice_dict["subtotal"], 1000.00)
        self.assertEqual(invoice_dict["tax_total"], 180.00)
        self.assertEqual(invoice_dict["grand_total"], 1180.00)
        
        # 2. Customer mapping (uses snapshots)
        self.assertEqual(customer_dict["name"], "Alpha Corp")
        self.assertEqual(customer_dict["address"], self.customer.full_billing_address)
        
        # 3. Items list
        self.assertEqual(len(items_list), 1)
        item = items_list[0]
        self.assertEqual(item["name"], "Consulting Services")
        self.assertEqual(item["taxable_value"], 1000.00)
        self.assertEqual(item["tax_amount"], 180.00)
        
        # 4. Company dict
        self.assertEqual(company_dict["name"], "Test PDF Org")
        self.assertEqual(company_dict["state_code"], "MH")

    def test_historical_integrity(self):
        """
        Changing Master Customer/Product must not affect the PDF adapter output for issued invoices.
        """
        # Change master records
        self.customer.name = "Beta Corp"
        self.customer.save()
        self.product.name = "Support Services"
        self.product.unit_price = Decimal("2000.00")
        self.product.save()
        
        # Adapter output must remain historically accurate
        invoice_dict, customer_dict, items_list, company_dict = invoice_to_pdf_dicts(self.invoice)
        
        self.assertEqual(customer_dict["name"], "Alpha Corp")
        self.assertEqual(items_list[0]["name"], "Consulting Services")
        self.assertEqual(items_list[0]["rate"], 1000.00)

    def test_preview_view_unauthorized(self):
        """
        Unauthenticated users cannot access preview.
        """
        url = reverse("billing:preview", kwargs={"uuid": self.invoice.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    def test_preview_view_organization_isolation(self):
        """
        Another organization's user cannot access this invoice preview.
        """
        other_user = User.objects.create_user(username="other_user", email="other@example.com", password="password123")
        Organization.objects.create(owner=other_user, business_name="Other Org")
        
        self.client.force_login(other_user)
        url = reverse("billing:preview", kwargs={"uuid": self.invoice.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_preview_view_success_inline(self):
        """
        Authorized user can view the PDF inline.
        """
        self.client.force_login(self.user)
        url = reverse("billing:preview", kwargs={"uuid": self.invoice.uuid})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn('inline; filename="Invoice_INV-001.pdf"', response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_preview_view_success_download(self):
        """
        ?download=1 triggers attachment content-disposition.
        """
        self.client.force_login(self.user)
        url = reverse("billing:preview", kwargs={"uuid": self.invoice.uuid})
        response = self.client.get(f"{url}?download=1")
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn('attachment; filename="Invoice_INV-001.pdf"', response["Content-Disposition"])

    def test_letterhead_on_vs_off(self):
        """
        Test that letterhead settings are respected.
        Note: The actual rendering is tested deeply in PDF tests, but we can verify the preference doesn't break our view.
        """
        self.client.force_login(self.user)
        url = reverse("billing:preview", kwargs={"uuid": self.invoice.uuid})
        
        # 1. Letterhead OFF (Default)
        response_off = self.client.get(url)
        self.assertEqual(response_off.status_code, 200)
        
        # 2. Letterhead ON
        pref = DocumentPreference.objects.get(user=self.user)
        pref.print_on_letterhead = True
        pref.save()
        
        # Add a dummy letterhead to organization to ensure it renders correctly with letterhead
        dummy_img = SimpleUploadedFile("dummy.jpg", b"file_content", content_type="image/jpeg")
        self.org.letterhead = dummy_img
        self.org.save()
        
        response_on = self.client.get(url)
        self.assertEqual(response_on.status_code, 200)
        
        # We can't easily assert visual differences in raw PDF bytes here, 
        # but passing 200 without raising exceptions proves integration works for both modes.
        self.assertNotEqual(response_off.content, response_on.content, "PDF bytes should differ with letterhead ON")
