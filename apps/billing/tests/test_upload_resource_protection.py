"""
apps/billing/tests/test_upload_resource_protection.py

Comprehensive test suite for Phase 5 File Upload & Image Resource Protection.
Tests server-side size limits, header-only dimension checks, format validation,
corrupt file handling, branding integration, and backup import size boundaries.
"""

import io
from unittest.mock import patch
from PIL import Image

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from django.contrib.auth import get_user_model

from apps.common.validators import (
    validate_image_file_size,
    validate_image_dimensions_and_format,
    MAX_IMAGE_UPLOAD_SIZE_BYTES,
    MAX_IMAGE_PIXEL_DIMENSIONS,
)
from apps.organization.forms import OrganizationSetupForm, OrganizationUpdateForm
from apps.organization.models import Organization, BankAccount

User = get_user_model()


class UploadResourceProtectionTest(TestCase):
    """Unit tests for Phase 5 upload boundaries and image validators."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser_upload",
            email="testuser_upload@example.com",
            password="Password123!",
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Upload Test Org",
            legal_business_name="Upload Test Org Legal",
            is_gst_registered=False,
            business_email="org_upload@example.com",
            phone_number="9876543210",
            address_line_1="123 Test St",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            country="India",
        )
        self.user.organization = self.org
        self.user.save()

    def _create_dummy_image(self, format="PNG", size=(100, 100), color=(255, 0, 0)):
        buf = io.BytesIO()
        img = Image.new("RGB", size, color=color)
        img.save(buf, format=format)
        buf.seek(0)
        ext = "png" if format.upper() == "PNG" else "jpg" if format.upper() == "JPEG" else "webp"
        return SimpleUploadedFile(f"test_image.{ext}", buf.getvalue(), content_type=f"image/{ext}")

    def test_01_valid_image_upload_succeeds(self):
        """Test 1: Valid image upload (PNG, JPEG, WebP) within limits passes validation."""
        for fmt in ["PNG", "JPEG", "WEBP"]:
            img_file = self._create_dummy_image(format=fmt, size=(200, 200))
            # Should not raise
            validate_image_dimensions_and_format(img_file)
            self.assertEqual(img_file.tell(), 0)

    def test_02_oversized_image_rejected_server_side(self):
        """Test 2: Image > 5 MB is rejected server-side."""
        large_bytes = b"x" * (MAX_IMAGE_UPLOAD_SIZE_BYTES + 100)
        large_file = SimpleUploadedFile("too_large.png", large_bytes, content_type="image/png")
        
        with self.assertRaises(ValidationError) as cm:
            validate_image_file_size(large_file)
        self.assertIn("File is too large", str(cm.exception))

    def test_03_oversized_image_rejected_before_expensive_processing(self):
        """Test 3: Oversized image is caught by size validator before Pillow Image.open is invoked."""
        large_bytes = b"x" * (MAX_IMAGE_UPLOAD_SIZE_BYTES + 500)
        large_file = SimpleUploadedFile("too_large.png", large_bytes, content_type="image/png")

        with patch("PIL.Image.open") as mock_open:
            with self.assertRaises(ValidationError):
                validate_image_dimensions_and_format(large_file)
            # Image.open must NOT be called if size check fails
            mock_open.assert_not_called()

    def test_04_excessive_image_dimensions_rejected(self):
        """Test 4: Image exceeding maximum dimensions (5000x5000 px) is rejected."""
        # Create small memory buffer with huge header dimensions (5001x100)
        buf = io.BytesIO()
        img = Image.new("RGB", (5001, 100), color="blue")
        img.save(buf, format="PNG")
        buf.seek(0)
        huge_dim_file = SimpleUploadedFile("huge_dim.png", buf.getvalue(), content_type="image/png")

        with self.assertRaises(ValidationError) as cm:
            validate_image_dimensions_and_format(huge_dim_file)
        self.assertIn("exceed the maximum allowed limit of 5000×5000 px", str(cm.exception))

    def test_05_corrupt_image_rejected_gracefully(self):
        """Test 5: Corrupt / malformed image file is rejected with clean ValidationError."""
        corrupt_file = SimpleUploadedFile("corrupt.png", b"NOT_AN_IMAGE_CONTENT_RANDOM_BYTES", content_type="image/png")

        with self.assertRaises(ValidationError) as cm:
            validate_image_dimensions_and_format(corrupt_file)
        self.assertIn("corrupt or invalid", str(cm.exception))

    def test_06_unsupported_image_type_rejected(self):
        """Test 6: Unsupported format (e.g. GIF or executable disguised as image) is rejected."""
        buf = io.BytesIO()
        img = Image.new("RGB", (50, 50), color="green")
        img.save(buf, format="GIF")
        buf.seek(0)
        gif_file = SimpleUploadedFile("animation.gif", buf.getvalue(), content_type="image/gif")

        with self.assertRaises(ValidationError) as cm:
            validate_image_dimensions_and_format(gif_file)
        self.assertIn("Unsupported image format", str(cm.exception))

    def test_07_valid_existing_image_formats_continue_working(self):
        """Test 7: Valid PNG, JPEG, and WebP images validate cleanly in forms."""
        png_img = self._create_dummy_image(format="PNG", size=(300, 300))
        form = OrganizationSetupForm(
            data={
                "business_name": "Setup Org",
                "is_gst_registered": False,
                "business_email": "setup@example.com",
                "phone_number": "9876543210",
                "address_line_1": "123 St",
                "city": "Mumbai",
                "state": "Maharashtra",
                "pincode": "400001",
                "country": "India",
            },
            files={"logo": png_img},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_08_backup_file_over_25mb_remains_rejected(self):
        """Test 8: Backup import upload > 25 MB remains rejected (Phase 4 integration)."""
        self.client.force_login(self.user)
        oversized_backup = SimpleUploadedFile("backup.xlsx", b"0" * (25 * 1024 * 1024 + 100), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        
        response = self.client.post(
            reverse("settings_app:excel_import_validate"),
            {"backup_file": oversized_backup},
        )
        self.assertEqual(response.status_code, 400)
        json_data = response.json()
        self.assertFalse(json_data["success"])
        self.assertIn("exceeds maximum allowed limit of 25 MB", json_data["message"])

    def test_09_form_validation_rejects_oversized_logo(self):
        """Test 9: OrganizationUpdateForm correctly handles oversized logo validation error."""
        large_file = self._create_dummy_image(format="PNG", size=(100, 100))
        # Override file size attribute to simulate oversized upload
        large_file.size = MAX_IMAGE_UPLOAD_SIZE_BYTES + 100

        form = OrganizationUpdateForm(
            data={
                "business_name": self.org.business_name,
                "legal_business_name": self.org.legal_business_name,
                "is_gst_registered": False,
                "business_email": self.org.business_email,
                "phone_number": self.org.phone_number,
                "address_line_1": self.org.address_line_1,
                "city": self.org.city,
                "state": self.org.state,
                "pincode": self.org.pincode,
                "country": self.org.country,
                "letterhead_header_offset": 30,
                "letterhead_footer_offset": 25,
                "signature_mode": "none",
            },
            files={"logo": large_file},
            instance=self.org,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("logo", form.errors)
        self.assertIn("Maximum allowed size is 5 MB", str(form.errors["logo"]))

    def test_10_existing_branding_functionality_remains_intact(self):
        """Test 10: Valid branding images are saved to Organization instance without breaking views."""
        self.client.force_login(self.user)
        logo_img = self._create_dummy_image(format="PNG", size=(150, 150))
        sig_img = self._create_dummy_image(format="PNG", size=(100, 50))

        response = self.client.post(
            reverse("organization:index"),
            data={
                "business_name": self.org.business_name,
                "legal_business_name": self.org.legal_business_name,
                "is_gst_registered": False,
                "business_email": self.org.business_email,
                "phone_number": self.org.phone_number,
                "address_line_1": self.org.address_line_1,
                "city": self.org.city,
                "state": self.org.state,
                "pincode": self.org.pincode,
                "country": self.org.country,
                "letterhead_header_offset": 30,
                "letterhead_footer_offset": 25,
                "signature_mode": "image",
                "logo": logo_img,
                "signature": sig_img,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.org.refresh_from_db()
        self.assertTrue(bool(self.org.logo))
        self.assertTrue(bool(self.org.signature))
