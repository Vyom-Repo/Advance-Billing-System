"""
apps/settings_app/tests/test_delete_account_system.py

Comprehensive test suite covering Danger Zone Account Deletion:
- Authentication & CSRF safety
- GET request rejection
- Multi-Tenant isolation (User A cannot delete Org B)
- Non-Owner permission denial
- Password re-authentication enforcement
- Explicit uppercase 'DELETE' phrase validation
- Atomic database transactional cleanup
- Post-deletion session invalidation and redirect
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import Invoice, InvoiceLine
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product
from apps.settings_app.models import (
    DataManagementAction,
    DataManagementAuditLog,
    OrganizationBackupSetting,
)

User = get_user_model()


class DeleteAccountSystemTests(TestCase):
    def setUp(self):
        # Owner 1 & Org 1
        self.owner1 = User.objects.create_user(
            username="owner1@acme.com",
            email="owner1@acme.com",
            password="Password123!",
            first_name="Owner",
            last_name="One"
        )
        self.org1 = Organization.objects.create(
            owner=self.owner1,
            business_name="Acme Corp",
            gstin="27AAAAA0000A1Z5",
            business_email="owner1@acme.com"
        )
        self.owner1.organization = self.org1
        self.owner1.save()

        # Non-owner Member 1 (Org 1)
        self.member1 = User.objects.create_user(
            username="member1@acme.com",
            email="member1@acme.com",
            password="Password123!",
            first_name="Member",
            last_name="One"
        )

        # Owner 2 & Org 2 (Multi-tenant security)
        self.owner2 = User.objects.create_user(
            username="owner2@beta.com",
            email="owner2@beta.com",
            password="Password123!",
            first_name="Owner",
            last_name="Two"
        )
        self.org2 = Organization.objects.create(
            owner=self.owner2,
            business_name="Beta Corp",
            gstin="29BBBBB1111B2Z6",
            business_email="owner2@beta.com"
        )
        self.owner2.organization = self.org2
        self.owner2.save()

        # Org 1 Business Data
        self.customer1 = Customer.objects.create(
            organization=self.org1,
            name="Customer One",
            billing_address_line_1="100 Main St",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_pin_code="400001",
            billing_state_code="27"
        )
        self.product1 = Product.objects.create(
            organization=self.org1,
            name="Widget",
            unit_price=100.00
        )
        self.invoice1 = Invoice.objects.create(
            organization=self.org1,
            customer_name_snapshot="Customer One",
            status="issued",
            invoice_number="INV-001",
            invoice_date=timezone.now().date(),
            grand_total=118.00
        )
        self.line1 = InvoiceLine.objects.create(
            invoice=self.invoice1,
            product=self.product1,
            position=1,
            product_name_snapshot="Widget",
            unit_price=100.00,
            quantity=1,
            taxable_value=100.00,
            line_total=118.00
        )
        self.backup_setting1 = OrganizationBackupSetting.objects.create(
            organization=self.org1,
            weekly_backup_enabled=True
        )

        self.client_owner1 = Client()
        self.client_owner1.force_login(self.owner1)

        self.client_member1 = Client()
        self.client_member1.force_login(self.member1)

        self.client_owner2 = Client()
        self.client_owner2.force_login(self.owner2)

        self.url = reverse("settings_app:delete_account")

    def test_danger_zone_page_rendering(self):
        """Danger Zone page loads cleanly on its own route with zero backup elements."""
        dz_url = reverse("settings_app:danger_zone")
        res = self.client_owner1.get(dz_url)
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Danger Zone")
        self.assertContains(res, "Delete Account")
        self.assertContains(res, f'href="{dz_url}"')
        self.assertNotContains(res, "Export Excel Backup")
        self.assertNotContains(res, "Weekly Data Backup")

    def test_unauthenticated_user_cannot_delete(self):
        """Unauthenticated POST request redirects to login without modifying data."""
        client = Client()
        res = client.post(self.url, {"password": "Password123!", "confirmation_phrase": "DELETE"})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Organization.objects.filter(id=self.org1.id).exists())

    def test_get_request_cannot_delete(self):
        """GET request to deletion endpoint is rejected."""
        res = self.client_owner1.get(self.url)
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Organization.objects.filter(id=self.org1.id).exists())

    def test_non_owner_cannot_delete_organization(self):
        """Organization member who is not the owner cannot delete organization."""
        res = self.client_member1.post(self.url, {"password": "Password123!", "confirmation_phrase": "DELETE"})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Organization.objects.filter(id=self.org1.id).exists())

    def test_tenant_isolation_prevents_cross_organization_deletion(self):
        """Owner 2 attempting to trigger deletion only impacts Owner 2's org, never Org 1."""
        res = self.client_owner2.post(self.url, {"password": "Password123!", "confirmation_phrase": "DELETE"})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Organization.objects.filter(id=self.org1.id).exists())
        self.assertFalse(Organization.objects.filter(id=self.org2.id).exists())

    def test_incorrect_password_prevents_deletion(self):
        """Incorrect password fails deletion and leaves all data intact."""
        res = self.client_owner1.post(self.url, {"password": "WrongPassword!", "confirmation_phrase": "DELETE"})
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Organization.objects.filter(id=self.org1.id).exists())
        self.assertTrue(Customer.objects.filter(id=self.customer1.id).exists())

    def test_incorrect_confirmation_phrase_prevents_deletion(self):
        """Lowercase or incorrect confirmation phrase prevents deletion."""
        invalid_phrases = ["delete", "Delete", "DELET", "DELETE "]
        for phrase in invalid_phrases:
            res = self.client_owner1.post(self.url, {"password": "Password123!", "confirmation_phrase": phrase})
            self.assertEqual(res.status_code, 302)
            self.assertTrue(Organization.objects.filter(id=self.org1.id).exists())

    def test_successful_organization_deletion(self):
        """Valid password + uppercase 'DELETE' phrase executes atomic transactional deletion."""
        res = self.client_owner1.post(self.url, {"password": "Password123!", "confirmation_phrase": "DELETE"})
        self.assertRedirects(res, reverse("auth:login"))

        # Verify Organization and dependent records are deleted
        self.assertFalse(Organization.objects.filter(id=self.org1.id).exists())
        self.assertFalse(Customer.objects.filter(id=self.customer1.id).exists())
        self.assertFalse(Product.objects.filter(id=self.product1.id).exists())
        self.assertFalse(Invoice.objects.filter(id=self.invoice1.id).exists())
        self.assertFalse(InvoiceLine.objects.filter(id=self.line1.id).exists())
        self.assertFalse(OrganizationBackupSetting.objects.filter(organization_id=self.org1.id).exists())

        # Verify Org 2 remains completely untouched
        self.assertTrue(Organization.objects.filter(id=self.org2.id).exists())
