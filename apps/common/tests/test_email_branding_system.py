"""
apps/common/tests/test_email_branding_system.py

Comprehensive test suite verifying that all Advance Billing outgoing emails
use Advance Billing product-level branding exclusively.
Organization/company logo and colors MUST NOT leak into email shells.
"""

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import Invoice
from apps.billing.services.invoice_email_service import InvoiceEmailService
from apps.common.services.email_service import AdvanceBillingEmailBranding
from apps.organization.models import Organization
from apps.settings_app.services.backup_service import OrganizationBackupService

User = get_user_model()


class AdvanceBillingProductEmailBrandingTests(TestCase):
    def setUp(self):
        # Organization 1 (With Custom Business Data)
        self.user1 = User.objects.create_user(
            username="owner1@acmecorp.com",
            email="owner1@acmecorp.com",
            password="Password123!",
            first_name="Alice",
            last_name="Owner"
        )
        self.org1 = Organization.objects.create(
            owner=self.user1,
            business_name="Acme Solutions Private Limited",
            business_email="support@acmecorp.com",
            phone_number="+91 98765 43210",
            address_line_1="Building 4, Tech Park",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001"
        )
        self.user1.organization = self.org1
        self.user1.save()

        # Organization 2 (For Multi-Tenant Identity Testing)
        self.user2 = User.objects.create_user(
            username="owner2@betacorp.com",
            email="owner2@betacorp.com",
            password="Password123!",
            first_name="Bob",
            last_name="Owner"
        )
        self.org2 = Organization.objects.create(
            owner=self.user2,
            business_name="Beta Global Enterprises",
            business_email="contact@betaglobal.com"
        )
        self.user2.organization = self.org2
        self.user2.save()

        self.invoice1 = Invoice.objects.create(
            organization=self.org1,
            customer_name_snapshot="John Doe",
            customer_billing_address_snapshot="123 Street",
            customer_state_code_snapshot="27",
            status="issued",
            invoice_number="INV-2026-0099",
            invoice_date=timezone.now().date(),
            grand_total=1250.00
        )

    def test_email_branding_resolver_returns_product_branding_only(self):
        """Resolver returns product-level Advance Billing branding regardless of org."""
        branding = AdvanceBillingEmailBranding.get_email_branding()
        self.assertEqual(branding["brand_name"], "Advance Billing")
        self.assertEqual(branding["app_name"], "Advance Billing")
        self.assertIn("Lora", branding["font_family"])
        self.assertEqual(branding["primary_color"], "#1E293B")
        self.assertEqual(branding["secondary_color"], "#FF7A00")

    def test_invoice_email_uses_advance_billing_shell(self):
        """Invoice email shell uses Advance Billing branding while org name is data content."""
        success, msg = InvoiceEmailService.send_invoice_email(self.invoice1)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        sent_email = mail.outbox[0]
        html_body = sent_email.alternatives[0][0]

        # Verify Advance Billing Product Branding in Header & Footer
        self.assertIn("Advance", html_body)
        self.assertIn("Billing", html_body)
        self.assertIn("Lora", html_body)
        self.assertIn("#1E293B", html_body)
        self.assertIn("#FF7A00", html_body)
        self.assertIn("Powered by Advance Billing", html_body)

        # Verify Organization Name appears as Plain Text Content
        self.assertIn("Acme Solutions Private Limited", html_body)

        # Verify PDF attachment
        self.assertEqual(len(sent_email.attachments), 1)
        self.assertTrue(sent_email.attachments[0][0].endswith(".pdf"))

    def test_weekly_backup_email_uses_advance_billing_shell(self):
        """Weekly backup email shell uses Advance Billing branding."""
        success, msg = OrganizationBackupService.send_weekly_backup_email(self.org1, force=True)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        sent_email = mail.outbox[0]
        html_body = sent_email.alternatives[0][0]

        self.assertIn("Advance", html_body)
        self.assertIn("Billing", html_body)
        self.assertIn("Lora", html_body)
        self.assertIn("Powered by Advance Billing", html_body)

        # Verify JSON & Excel attachments (2 attachments)
        self.assertEqual(len(sent_email.attachments), 2)
        self.assertTrue(sent_email.attachments[0][0].endswith(".json"))
        self.assertTrue(sent_email.attachments[1][0].endswith(".xlsx"))

    def test_instant_backup_email_uses_advance_billing_shell(self):
        """Instant backup email shell uses Advance Billing branding."""
        from apps.settings_app.models import BackupTrigger
        success, msg = OrganizationBackupService.send_weekly_backup_email(
            self.org1, force=True, trigger=BackupTrigger.MANUAL
        )
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        sent_email = mail.outbox[0]
        html_body = sent_email.alternatives[0][0]

        self.assertIn("Advance", html_body)
        self.assertIn("Billing", html_body)
        self.assertIn("Lora", html_body)

    def test_multi_tenant_branding_identity_consistency(self):
        """Emails for Org 1 and Org 2 use identical Advance Billing branding shell; only content differs."""
        InvoiceEmailService.send_invoice_email(self.invoice1)
        OrganizationBackupService.send_weekly_backup_email(self.org2, force=True)

        email_org1_html = mail.outbox[0].alternatives[0][0]
        email_org2_html = mail.outbox[1].alternatives[0][0]

        # Both use Advance Billing Header & Lora Font
        self.assertIn("Advance", email_org1_html)
        self.assertIn("Advance", email_org2_html)
        self.assertIn("Lora", email_org1_html)
        self.assertIn("Lora", email_org2_html)

        # Content differences only
        self.assertIn("Acme Solutions Private Limited", email_org1_html)
        self.assertIn("Beta Global Enterprises", email_org2_html)

    def test_mailto_link_href_contains_only_raw_email(self):
        """Verify mailto href contains ONLY raw email address and visible text is Advance Billing."""
        branding = AdvanceBillingEmailBranding.get_email_branding()
        self.assertEqual(branding["support_email"], "advancebillingbyvyom@gmail.com")
        self.assertEqual(branding["support_email_address"], "advancebillingbyvyom@gmail.com")
        self.assertEqual(branding["support_email_display_name"], "Advance Billing")
        self.assertEqual(branding["support_email_display"], "Advance Billing <advancebillingbyvyom@gmail.com>")
        self.assertEqual(branding["support_mailto_url"], "mailto:advancebillingbyvyom@gmail.com")

        # Test email template rendering
        InvoiceEmailService.send_invoice_email(self.invoice1)
        sent_email = mail.outbox[0]
        html_body = sent_email.alternatives[0][0]

        # 1. Check href contains ONLY clean raw email address
        self.assertIn('href="mailto:advancebillingbyvyom@gmail.com"', html_body)

        # 2. Check visible display text is Advance Billing
        self.assertIn('Advance Billing</a>', html_body)
        self.assertNotIn('Advance Billing &lt;advancebillingbyvyom@gmail.com&gt;', html_body)

        # 3. Assert NO malformed encoded display name or + in mailto recipient
        self.assertNotIn('mailto:Advance', html_body)
        self.assertNotIn('mailto:Advance+Billing', html_body)
        self.assertNotIn('mailto:Advance%20Billing', html_body)

    def test_all_email_templates_render_clean_mailto_link(self):
        """Verify that verification, password reset, OTP, and backup emails all render clean mailto href."""
        from apps.common.services.email_service import EmailService

        # 1. Verification Email
        EmailService.send_verification_email(self.user1, "https://example.com/verify")
        # 2. Password Reset Email
        EmailService.send_password_reset_email(self.user1, "https://example.com/reset")
        # 3. OTP Email
        EmailService.send_otp_email(self.user1, "123456")
        # 4. Backup Email
        OrganizationBackupService.send_weekly_backup_email(self.org1, force=True)

        self.assertGreaterEqual(len(mail.outbox), 4)

        for sent_mail in mail.outbox:
            if sent_mail.alternatives:
                html = sent_mail.alternatives[0][0]
                self.assertIn('href="mailto:advancebillingbyvyom@gmail.com"', html)
                self.assertIn('Advance Billing</a>', html)
                self.assertNotIn('mailto:Advance', html)
                self.assertNotIn('mailto:Advance+Billing', html)
                self.assertNotIn('mailto:Advance%20Billing', html)

    def test_mailto_parsing_handles_formatted_setting(self):
        """Even if SERVER_EMAIL is formatted 'Advance Billing <advancebillingbyvyom@gmail.com>', parseaddr extracts raw address."""
        from django.test import override_settings
        with override_settings(SERVER_EMAIL="Advance Billing <advancebillingbyvyom@gmail.com>", SUPPORT_EMAIL="Advance Billing <advancebillingbyvyom@gmail.com>"):
            branding = AdvanceBillingEmailBranding.get_email_branding()
            self.assertEqual(branding["support_email"], "advancebillingbyvyom@gmail.com")
            self.assertEqual(branding["support_email_address"], "advancebillingbyvyom@gmail.com")
            self.assertEqual(branding["support_email_display_name"], "Advance Billing")
            self.assertEqual(branding["support_mailto_url"], "mailto:advancebillingbyvyom@gmail.com")

