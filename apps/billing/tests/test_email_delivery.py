"""
apps/billing/tests/test_email_delivery.py

Comprehensive test suite for Invoice PDF Email Delivery to Organization Owner & On-Demand Mail System.
"""

from decimal import Decimal
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.organization.models import Organization
from apps.customers.models import Customer, CustomerType, GSTStatus
from apps.products.models import Product, ProductType, TaxabilityType, PriceBasis
from apps.billing.models import Invoice, InvoiceStatus, InvoiceLine, EmailStatus, EmailTrigger
from apps.billing.services.calculation_engine import finalize_invoice
from apps.billing.services.invoice_email_service import InvoiceEmailService

User = get_user_model()


class InvoiceOwnerEmailDeliveryBaseTest(TestCase):

    def setUp(self):
        super().setUp()
        # Create Org 1 Owner with email
        self.owner1 = User.objects.create_user(
            username="org1_owner",
            email="owner1@acme.com",
            password="password123",
            first_name="Alice"
        )
        self.org1 = Organization.objects.create(
            business_name="Acme Corp",
            owner=self.owner1,
            business_email="contact@acme.com",
            state_code="27",
            address_line_1="100 Acme Way",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001"
        )

        # Create Customer (NO email required on customer model)
        self.customer1 = Customer.objects.create(
            organization=self.org1,
            customer_type=CustomerType.BUSINESS,
            gst_status=GSTStatus.UNREGISTERED,
            name="Alpha Traders",
            billing_address_line_1="1 Red Street",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_state_code="27",
            billing_pin_code="400002"
        )

        # Product
        self.product1 = Product.objects.create(
            organization=self.org1,
            name="Widget A",
            product_type=ProductType.GOODS,
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            unit_price=Decimal("100.00"),
            price_basis=PriceBasis.EXCLUSIVE
        )

        # Org 2 and Owner 2 (for multi-tenant isolation testing)
        self.owner2 = User.objects.create_user(
            username="org2_owner",
            email="owner2@beta.com",
            password="password123",
            first_name="Bob"
        )
        self.org2 = Organization.objects.create(
            business_name="Beta Logistics",
            owner=self.owner2,
            business_email="contact@beta.com",
            state_code="27",
            address_line_1="200 Beta Road",
            city="Mumbai",
            state="Maharashtra",
            pincode="400005"
        )


class AutomaticInvoiceEmailToOwnerTests(InvoiceOwnerEmailDeliveryBaseTest):

    def test_automatic_email_sent_to_organization_owner(self):
        """Issuing an invoice emails the PDF to the organization owner, NOT the customer."""
        invoice = Invoice.objects.create(
            organization=self.org1,
            customer=self.customer1,
            invoice_date="2026-08-26",
            place_of_supply="27",
            customer_name_snapshot=self.customer1.name,
            customer_billing_address_snapshot=self.customer1.full_billing_address,
            customer_state_code_snapshot=self.customer1.billing_state_code
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            position=1,
            product=self.product1,
            product_name_snapshot=self.product1.name,
            product_type_snapshot=self.product1.product_type,
            hsn_sac_snapshot="1234",
            taxability_type_snapshot=self.product1.taxability_type,
            gst_rate_snapshot=self.product1.gst_rate,
            price_basis_snapshot=self.product1.price_basis,
            uqc_snapshot="NOS",
            quantity=Decimal("2"),
            unit_price=Decimal("100.00")
        )

        with self.captureOnCommitCallbacks(execute=True):
            issued = finalize_invoice(invoice)

        import time
        for _ in range(50):
            if len(mail.outbox) > 0:
                break
            time.sleep(0.1)

        self.assertEqual(issued.status, InvoiceStatus.ISSUED)
        self.assertIsNotNone(issued.invoice_number)

        # Verify email outbox - must go to owner1@acme.com
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ["owner1@acme.com"])
        self.assertIn("Copy", sent_email.subject)
        self.assertIn(issued.invoice_number, sent_email.subject)

        # Verify PDF attachment
        self.assertEqual(len(sent_email.attachments), 1)
        attachment_name, attachment_content, mimetype = sent_email.attachments[0]
        self.assertTrue(attachment_name.endswith(".pdf"))
        self.assertEqual(mimetype, "application/pdf")
        self.assertTrue(attachment_content.startswith(b"%PDF"))

        # Verify audit fields on invoice
        issued.refresh_from_db()
        self.assertTrue(issued.email_sent)
        self.assertEqual(issued.email_last_status, EmailStatus.SENT)
        self.assertEqual(issued.email_last_trigger, EmailTrigger.AUTOMATIC)
        self.assertEqual(issued.email_recipient, "owner1@acme.com")
        self.assertIsNotNone(issued.email_last_sent_at)

    def test_duplicate_issue_prevention(self):
        """Finalized/Issued invoices cannot be issued again or re-trigger automatic email."""
        invoice = Invoice.objects.create(
            organization=self.org1,
            customer=self.customer1,
            invoice_date="2026-08-26",
            place_of_supply="27",
            customer_name_snapshot=self.customer1.name,
            customer_billing_address_snapshot=self.customer1.full_billing_address,
            customer_state_code_snapshot=self.customer1.billing_state_code
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            position=1,
            product=self.product1,
            product_name_snapshot=self.product1.name,
            product_type_snapshot=self.product1.product_type,
            hsn_sac_snapshot="1234",
            taxability_type_snapshot=self.product1.taxability_type,
            gst_rate_snapshot=self.product1.gst_rate,
            price_basis_snapshot=self.product1.price_basis,
            uqc_snapshot="NOS",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00")
        )

        with self.captureOnCommitCallbacks(execute=True):
            issued = finalize_invoice(invoice)

        import time
        for _ in range(50):
            if len(mail.outbox) > 0:
                break
            time.sleep(0.1)

        self.assertEqual(len(mail.outbox), 1)

        # Calling finalize_invoice on already issued invoice raises ValidationError
        with self.assertRaises(ValidationError):
            finalize_invoice(issued)

        self.assertEqual(len(mail.outbox), 1)


class ManualInvoiceMailOwnerActionTests(InvoiceOwnerEmailDeliveryBaseTest):

    def test_manual_mail_action_emails_owner(self):
        """User clicking Mail action sends email copy to the organization owner."""
        invoice = Invoice.objects.create(
            organization=self.org1,
            customer=self.customer1,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-2026-0001",
            invoice_date="2026-08-26",
            place_of_supply="27",
            customer_name_snapshot=self.customer1.name,
            customer_billing_address_snapshot=self.customer1.full_billing_address,
            customer_state_code_snapshot=self.customer1.billing_state_code,
            grand_total=Decimal("236.00")
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            position=1,
            product=self.product1,
            product_name_snapshot=self.product1.name,
            product_type_snapshot=self.product1.product_type,
            hsn_sac_snapshot="1234",
            taxability_type_snapshot=self.product1.taxability_type,
            gst_rate_snapshot=self.product1.gst_rate,
            price_basis_snapshot=self.product1.price_basis,
            uqc_snapshot="NOS",
            quantity=Decimal("2"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("236.00")
        )

        self.client.force_login(self.owner1)
        url = reverse("billing:mail", kwargs={"uuid": invoice.uuid})
        response = self.client.post(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invoice copy emailed successfully to the organization owner.")

        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.to, ["owner1@acme.com"])

        invoice.refresh_from_db()
        self.assertTrue(invoice.email_sent)
        self.assertEqual(invoice.email_last_status, EmailStatus.SENT)
        self.assertEqual(invoice.email_last_trigger, EmailTrigger.MANUAL)
        self.assertEqual(invoice.email_recipient, "owner1@acme.com")

    def test_manual_mail_re_sending_allowed(self):
        """Manual mailing can be executed multiple times even if email_sent is already True."""
        invoice = Invoice.objects.create(
            organization=self.org1,
            customer=self.customer1,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-2026-0002",
            invoice_date="2026-08-26",
            place_of_supply="27",
            customer_name_snapshot=self.customer1.name,
            customer_billing_address_snapshot=self.customer1.full_billing_address,
            customer_state_code_snapshot=self.customer1.billing_state_code,
            email_sent=True,
            email_last_status=EmailStatus.SENT,
            email_last_trigger=EmailTrigger.AUTOMATIC,
            email_recipient="owner1@acme.com"
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            position=1,
            product=self.product1,
            product_name_snapshot=self.product1.name,
            product_type_snapshot=self.product1.product_type,
            hsn_sac_snapshot="1234",
            taxability_type_snapshot=self.product1.taxability_type,
            gst_rate_snapshot=self.product1.gst_rate,
            price_basis_snapshot=self.product1.price_basis,
            uqc_snapshot="NOS",
            quantity=Decimal("1"),
            unit_price=Decimal("100.00")
        )

        self.client.force_login(self.owner1)
        url = reverse("billing:mail", kwargs={"uuid": invoice.uuid})
        response = self.client.post(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invoice copy emailed successfully to the organization owner.")
        self.assertEqual(len(mail.outbox), 1)

        invoice.refresh_from_db()
        self.assertEqual(invoice.email_last_trigger, EmailTrigger.MANUAL)

    def test_manual_mail_missing_owner_email_error(self):
        """Mailing an invoice whose org owner has no email fails gracefully with clean message."""
        self.owner1.email = ""
        self.owner1.save()

        invoice = Invoice.objects.create(
            organization=self.org1,
            customer=self.customer1,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-2026-0003",
            invoice_date="2026-08-26",
            place_of_supply="27",
            customer_name_snapshot=self.customer1.name,
            customer_billing_address_snapshot=self.customer1.full_billing_address,
            customer_state_code_snapshot=self.customer1.billing_state_code
        )

        self.client.force_login(self.owner1)
        url = reverse("billing:mail", kwargs={"uuid": invoice.uuid})
        response = self.client.post(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The organization owner does not have a valid email address.")
        self.assertEqual(len(mail.outbox), 0)

        invoice.refresh_from_db()
        self.assertEqual(invoice.email_last_status, EmailStatus.FAILED)
        self.assertIn("does not have a valid email address", invoice.email_last_error)


class FailureHandlingOwnerEmailTests(InvoiceOwnerEmailDeliveryBaseTest):

    @patch("apps.billing.services.invoice_email_service.InvoiceEmailService.generate_pdf_bytes")
    def test_pdf_generation_failure_handling(self, mock_pdf):
        """If PDF generation fails, email is not sent and failure audit is logged."""
        mock_pdf.side_effect = Exception("Weasyprint rendering failed")

        invoice = Invoice.objects.create(
            organization=self.org1,
            customer=self.customer1,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-2026-0004",
            invoice_date="2026-08-26",
            place_of_supply="27",
            customer_name_snapshot=self.customer1.name,
            customer_billing_address_snapshot=self.customer1.full_billing_address,
            customer_state_code_snapshot=self.customer1.billing_state_code
        )

        success, msg = InvoiceEmailService.send_invoice_email(invoice, trigger=EmailTrigger.MANUAL)

        self.assertFalse(success)
        self.assertIn("Failed to generate invoice PDF", msg)
        self.assertEqual(len(mail.outbox), 0)

        invoice.refresh_from_db()
        self.assertEqual(invoice.email_last_status, EmailStatus.FAILED)
        self.assertIn("PDF Generation Error", invoice.email_last_error)

    @patch("django.core.mail.EmailMultiAlternatives.send")
    def test_smtp_failure_handling(self, mock_send):
        """If SMTP sending fails, invoice financial state is untouched and failure is recorded."""
        mock_send.side_effect = Exception("SMTP Connection refused")

        invoice = Invoice.objects.create(
            organization=self.org1,
            customer=self.customer1,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-2026-0005",
            invoice_date="2026-08-26",
            place_of_supply="27",
            customer_name_snapshot=self.customer1.name,
            customer_billing_address_snapshot=self.customer1.full_billing_address,
            customer_state_code_snapshot=self.customer1.billing_state_code,
            grand_total=Decimal("500.00")
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            position=1,
            product=self.product1,
            product_name_snapshot=self.product1.name,
            product_type_snapshot=self.product1.product_type,
            hsn_sac_snapshot="1234",
            taxability_type_snapshot=self.product1.taxability_type,
            gst_rate_snapshot=self.product1.gst_rate,
            price_basis_snapshot=self.product1.price_basis,
            uqc_snapshot="NOS",
            quantity=Decimal("1"),
            unit_price=Decimal("500.00"),
            line_total=Decimal("500.00")
        )

        success, msg = InvoiceEmailService.send_invoice_email(invoice, trigger=EmailTrigger.MANUAL)

        self.assertFalse(success)
        invoice.refresh_from_db()
        self.assertEqual(invoice.email_last_status, EmailStatus.FAILED)
        self.assertIn("SMTP Connection refused", invoice.email_last_error)
        self.assertEqual(invoice.grand_total, Decimal("500.00"))


class MultiTenantSecurityOwnerEmailTests(InvoiceOwnerEmailDeliveryBaseTest):

    def test_cross_organization_mail_action_rejected(self):
        """User from Org 2 cannot trigger mail action against Org 1's invoice (returns 404)."""
        invoice_org1 = Invoice.objects.create(
            organization=self.org1,
            customer=self.customer1,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-2026-0006",
            invoice_date="2026-08-26",
            place_of_supply="27",
            customer_name_snapshot=self.customer1.name,
            customer_billing_address_snapshot=self.customer1.full_billing_address,
            customer_state_code_snapshot=self.customer1.billing_state_code
        )

        # Log in as User 2 (Org 2 owner)
        self.client.force_login(self.owner2)
        url = reverse("billing:mail", kwargs={"uuid": invoice_org1.uuid})

        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)
