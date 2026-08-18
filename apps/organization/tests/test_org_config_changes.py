"""
apps/organization/tests/test_org_config_changes.py

Unit and integration tests for Organization invoice configuration changes:
- QR Code upload and removal
- Terms & Conditions persistence
- Bank Account deletion
- Context variables (has_qr, has_terms) in invoice design view
- Bill serializer QR code and Terms fallback
"""
import tempfile
from PIL import Image
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.organization.models import Organization, BankAccount
from apps.organization.forms import OrganizationUpdateForm, OrganizationSetupForm
from apps.common.services.organization_service import OrganizationService
from apps.invoices.services.bill_serializer import serialize_bill_for_render

User = get_user_model()


def create_test_image():
    file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    image = Image.new("RGB", (100, 100), color="blue")
    image.save(file, format="PNG")
    file.seek(0)
    return SimpleUploadedFile(file.name, file.read(), content_type="image/png")


class OrganizationConfigChangesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="orgtestuser",
            email="orgtest@example.com",
            password="password123",
            first_name="Org",
            last_name="Test",
        )
        self.client = Client()
        self.client.login(username="orgtestuser", password="password123")

        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Test Corp",
            legal_business_name="Test Corp Pvt Ltd",
            gstin="27AAAAA0000A1Z5",
            pan="AAAAA0000A",
            state_code="27",
            address_line_1="123 Main St",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            country="India",
            business_email="test@corp.com",
            phone_number="9876543210",
        )

    def test_organization_setup_form_preserves_compulsory_fields(self):
        """Verify OrganizationSetupForm remains unchanged and strictly includes original fields."""
        form = OrganizationSetupForm()
        self.assertIn("business_name", form.fields)
        self.assertNotIn("qr_code", form.fields)
        self.assertNotIn("terms_and_conditions", form.fields)

    def test_qr_code_upload_and_removal(self):
        """Test uploading QR code image and removing it using virtual remove_qr_code field."""
        qr_img = create_test_image()
        form_data = {
            "business_name": "Test Corp",
            "legal_business_name": "Test Corp Pvt Ltd",
            "gstin": "27AAAAA0000A1Z5",
            "pan": "AAAAA0000A",
            "state_code": "27",
            "address_line_1": "123 Main St",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "country": "India",
            "business_email": "test@corp.com",
            "phone_number": "9876543210",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "terms_and_conditions": "Payment due within 30 days.",
            "signature_mode": "none",
            "remove_qr_code": "False",
        }
        form = OrganizationUpdateForm(data=form_data, files={"qr_code": qr_img}, instance=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.org.refresh_from_db()
        self.assertTrue(bool(self.org.qr_code))
        self.assertEqual(self.org.terms_and_conditions, "Payment due within 30 days.")

        # Remove QR code
        remove_form_data = form_data.copy()
        remove_form_data["remove_qr_code"] = "True"
        form_remove = OrganizationUpdateForm(data=remove_form_data, instance=self.org)
        self.assertTrue(form_remove.is_valid(), form_remove.errors)
        form_remove.save()
        self.org.refresh_from_db()
        self.assertFalse(bool(self.org.qr_code))

    def test_bank_account_deletion_backend(self):
        """Test deleting non-default and default bank accounts."""
        bank1 = BankAccount.objects.create(
            organization=self.org,
            bank_name="HDFC Bank",
            account_name="Test Corp",
            account_number="1234567890",
            ifsc_code="HDFC0001234",
            branch="Main Branch",
            is_default=True,
        )
        bank2 = BankAccount.objects.create(
            organization=self.org,
            bank_name="ICICI Bank",
            account_name="Test Corp",
            account_number="0987654321",
            ifsc_code="ICIC0005678",
            branch="Main Branch",
            is_default=False,
        )

        # Delete non-default bank
        response = self.client.post(reverse("organization:bank_delete", kwargs={"pk": bank2.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BankAccount.objects.filter(pk=bank2.pk).exists())
        bank1.refresh_from_db()
        self.assertTrue(bank1.is_default)

        # Delete default bank -> remaining bank (if any) promoted
        bank3 = BankAccount.objects.create(
            organization=self.org,
            bank_name="Axis Bank",
            account_name="Test Corp",
            account_number="1122334455",
            ifsc_code="UTIB0009999",
            branch="Main Branch",
            is_default=False,
        )
        response = self.client.post(reverse("organization:bank_delete", kwargs={"pk": bank1.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BankAccount.objects.filter(pk=bank1.pk).exists())
        bank3.refresh_from_db()
        self.assertTrue(bank3.is_default)

    def test_invoice_design_context_flags(self):
        """Verify has_qr and has_terms context variables in SettingsInvoiceDesignView."""
        url = reverse("settings_app:invoice_design")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_qr"])
        self.assertFalse(response.context["has_terms"])

        # Populate org QR and Terms
        qr_img = create_test_image()
        self.org.qr_code = qr_img
        self.org.terms_and_conditions = "Standard invoice terms."
        self.org.save()

        response2 = self.client.get(url)
        self.assertEqual(response2.status_code, 200)
        self.assertTrue(response2.context["has_qr"])
        self.assertTrue(response2.context["has_terms"])

    def test_bill_serializer_populates_qr_and_terms_from_org(self):
        """Verify serialize_bill_for_render populates bill.qr_code_url and bill.terms from Organization."""
        qr_img = create_test_image()
        self.org.qr_code = qr_img
        self.org.terms_and_conditions = "Default Org Terms"
        self.org.save()

        comp_dict = OrganizationService.get_company_assets(self.user)
        result = serialize_bill_for_render(
            invoice={"number": "INV-001"},
            customer={},
            items=[],
            company=comp_dict,
            org=self.org,
        )

        self.assertIn("qr_code_url", result["bill"])
        self.assertIsNotNone(result["bill"]["qr_code_url"])
        self.assertEqual(result["bill"]["terms"], "Default Org Terms")
        self.assertEqual(result["company"]["terms_and_conditions"], "Default Org Terms")
