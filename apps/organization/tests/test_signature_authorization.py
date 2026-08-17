"""
apps/organization/tests/test_signature_authorization.py
Tests for Signature / Authorization Modes and Computer-Generated Disclaimer.
"""
import tempfile
from PIL import Image
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from apps.organization.models import Organization, SignatureMode
from apps.organization.forms import OrganizationUpdateForm
from apps.common.services.organization_service import OrganizationService
from apps.invoices.services.bill_serializer import _serialize_company

User = get_user_model()


def create_test_image():
    file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    image = Image.new("RGB", (100, 100), color="blue")
    image.save(file, format="PNG")
    file.seek(0)
    return SimpleUploadedFile(file.name, file.read(), content_type="image/png")


class SignatureAuthorizationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="password123"
        )
        self.client = Client()
        self.client.login(username="testuser", password="password123")

        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Test Business",
            business_email="biz@example.com",
            phone_number="9876543210",
            address_line_1="123 Street",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            country="India",
            signature_mode=SignatureMode.NONE,
        )

    def test_default_organization_signature_mode(self):
        """Test default signature mode is 'none'."""
        self.assertEqual(self.org.signature_mode, SignatureMode.NONE)
        self.assertEqual(self.org.authorized_signatory_name, "")
        self.assertFalse(self.org.show_computer_generated_disclaimer)

    def test_form_validation_authorized_signatory_requires_name(self):
        """Form validation fails if authorized_signatory mode is selected without a name."""
        data = {
            "business_name": "Test Business",
            "business_email": "biz@example.com",
            "phone_number": "9876543210",
            "address_line_1": "123 Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "country": "India",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "signature_mode": "authorized_signatory",
            "authorized_signatory_name": "   ",
        }
        form = OrganizationUpdateForm(data=data, instance=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("authorized_signatory_name", form.errors)

    def test_form_validation_image_mode_requires_image(self):
        """Form validation fails if signature_mode='image' but no image uploaded or present."""
        data = {
            "business_name": "Test Business",
            "business_email": "biz@example.com",
            "phone_number": "9876543210",
            "address_line_1": "123 Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "country": "India",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "signature_mode": "image",
        }
        form = OrganizationUpdateForm(data=data, instance=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("signature_mode", form.errors)

    def test_form_validation_image_mode_with_valid_image(self):
        """Form validation succeeds when signature_mode='image' and file uploaded."""
        sample_img = create_test_image()
        data = {
            "business_name": "Test Business",
            "business_email": "biz@example.com",
            "phone_number": "9876543210",
            "address_line_1": "123 Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "country": "India",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "signature_mode": "image",
        }
        files = {"signature": sample_img}
        form = OrganizationUpdateForm(data=data, files=files, instance=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        saved_org = form.save()
        self.assertEqual(saved_org.signature_mode, "image")
        self.assertTrue(bool(saved_org.signature))

    def test_mode_switching_preserves_signature_file(self):
        """Switching signature_mode to 'none' or 'authorized_signatory' must NOT delete the signature image."""
        sample_img = create_test_image()
        self.org.signature = sample_img
        self.org.signature_mode = SignatureMode.IMAGE
        self.org.save()
        self.assertTrue(bool(self.org.signature))

        # Switch to authorized_signatory mode
        data = {
            "business_name": "Test Business",
            "business_email": "biz@example.com",
            "phone_number": "9876543210",
            "address_line_1": "123 Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "country": "India",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "signature_mode": "authorized_signatory",
            "authorized_signatory_name": "Authorized Signatory Officer",
        }
        form = OrganizationUpdateForm(data=data, instance=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        saved_org = form.save()

        # Image file must STILL exist in database and on disk
        self.assertEqual(saved_org.signature_mode, "authorized_signatory")
        self.assertEqual(saved_org.authorized_signatory_name, "Authorized Signatory Officer")
        self.assertTrue(bool(saved_org.signature))

    def test_explicit_remove_signature_deletes_file(self):
        """Explicitly setting remove_signature=True deletes the stored signature file."""
        sample_img = create_test_image()
        self.org.signature = sample_img
        self.org.signature_mode = SignatureMode.IMAGE
        self.org.save()

        data = {
            "business_name": "Test Business",
            "business_email": "biz@example.com",
            "phone_number": "9876543210",
            "address_line_1": "123 Street",
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": "400001",
            "country": "India",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "signature_mode": "none",
            "remove_signature": True,
        }
        form = OrganizationUpdateForm(data=data, instance=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        saved_org = form.save()
        self.assertFalse(bool(saved_org.signature))

    def test_organization_service_get_company_assets(self):
        """Test OrganizationService returns signature_mode, authorized_signatory_name, and disclaimer."""
        self.org.signature_mode = SignatureMode.AUTHORIZED_SIGNATORY
        self.org.authorized_signatory_name = "Jane Doe"
        self.org.show_computer_generated_disclaimer = True
        self.org.save()

        assets = OrganizationService.get_company_assets(self.user)
        self.assertEqual(assets["signature_mode"], "authorized_signatory")
        self.assertEqual(assets["authorized_signatory_name"], "Jane Doe")
        self.assertTrue(assets["show_computer_generated_disclaimer"])

    def test_bill_serializer_company_dict(self):
        """Test _serialize_company passes signature configuration attributes."""
        self.org.signature_mode = SignatureMode.AUTHORIZED_SIGNATORY
        self.org.authorized_signatory_name = "Jane Doe"
        self.org.show_computer_generated_disclaimer = True
        self.org.save()

        serialized = _serialize_company({}, self.org)
        self.assertEqual(serialized["signature_mode"], "authorized_signatory")
        self.assertEqual(serialized["authorized_signatory_name"], "Jane Doe")
        self.assertTrue(serialized["show_computer_generated_disclaimer"])

    def test_settings_invoice_design_view_has_signature_logic(self):
        """Test has_signature in SettingsInvoiceDesignView context across all modes via client GET."""
        url = reverse("settings_app:invoice_design")

        # Mode: None
        self.org.signature_mode = SignatureMode.NONE
        self.org.save()
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.context['has_signature'])

        # Mode: Image without image
        self.org.signature_mode = SignatureMode.IMAGE
        self.org.signature = None
        self.org.save()
        res = self.client.get(url)
        self.assertFalse(res.context['has_signature'])

        # Mode: Image with image
        sample_img = create_test_image()
        self.org.signature = sample_img
        self.org.save()
        res = self.client.get(url)
        self.assertTrue(res.context['has_signature'])

        # Mode: Authorized Signatory without name
        self.org.signature_mode = SignatureMode.AUTHORIZED_SIGNATORY
        self.org.authorized_signatory_name = ""
        self.org.save()
        res = self.client.get(url)
        self.assertFalse(res.context['has_signature'])

        # Mode: Authorized Signatory with name
        self.org.authorized_signatory_name = "ACME Manager"
        self.org.save()
        res = self.client.get(url)
        self.assertTrue(res.context['has_signature'])
