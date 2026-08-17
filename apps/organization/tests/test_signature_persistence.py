"""
apps/organization/tests/test_signature_persistence.py
Detailed verification of the persistence flow for Signature / Authorization from Organization Settings to Invoice Design.
"""
import tempfile
from PIL import Image
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from apps.organization.models import Organization, SignatureMode
from apps.settings_app.models import DocumentPreference

User = get_user_model()


def create_test_image():
    file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    image = Image.new("RGB", (100, 100), color="blue")
    image.save(file, format="PNG")
    file.seek(0)
    return SimpleUploadedFile(file.name, file.read(), content_type="image/png")


class SignaturePersistenceFlowTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="persistence_user",
            email="persist@example.com",
            password="password123"
        )
        self.client = Client()
        self.client.login(username="persistence_user", password="password123")

        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Samruddhi Enterprises",
            legal_business_name="Samruddhi Enterprises Pvt Ltd",
            gstin="27AAAAA0000A1Z5",
            pan="AAAAA0000A",
            state_code="27",
            address_line_1="456 Industrial Area",
            city="Pune",
            state="Maharashtra",
            pincode="411001",
            country="India",
            business_email="samruddhi@example.com",
            phone_number="9123456789",
            signature_mode=SignatureMode.NONE,
        )

        self.org_url = reverse("organization:index")
        self.design_url = reverse("settings_app:invoice_design")

    def test_1_persist_signature_mode_none(self):
        """Verify selecting None persists signature_mode to Organization and survives page reload."""
        post_data = {
            "business_name": "Samruddhi Enterprises",
            "business_email": "samruddhi@example.com",
            "phone_number": "9123456789",
            "address_line_1": "456 Industrial Area",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411001",
            "country": "India",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "signature_mode": "none",
        }
        res = self.client.post(self.org_url, data=post_data, follow=True)
        self.assertEqual(res.status_code, 200)

        # Reload Organization page
        reload_res = self.client.get(self.org_url)
        self.assertEqual(reload_res.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.signature_mode, "none")
        self.assertIn('name="signature_mode" value="none" checked', reload_res.content.decode("utf-8"))

    def test_2_persist_authorized_signatory_mode_and_name(self):
        """Verify selecting Authorized Signatory persists signature_mode and authorized_signatory_name."""
        post_data = {
            "business_name": "Samruddhi Enterprises",
            "business_email": "samruddhi@example.com",
            "phone_number": "9123456789",
            "address_line_1": "456 Industrial Area",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411001",
            "country": "India",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "signature_mode": "authorized_signatory",
            "authorized_signatory_name": "Samruddhi Enterprises Director",
            "show_computer_generated_disclaimer": "True",
        }
        res = self.client.post(self.org_url, data=post_data, follow=True)
        self.assertEqual(res.status_code, 200)

        # Reload Organization page
        reload_res = self.client.get(self.org_url)
        self.assertEqual(reload_res.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.signature_mode, "authorized_signatory")
        self.assertEqual(self.org.authorized_signatory_name, "Samruddhi Enterprises Director")
        self.assertTrue(self.org.show_computer_generated_disclaimer)
        self.assertIn('value="Samruddhi Enterprises Director"', reload_res.content.decode("utf-8"))

    def test_3_switching_mode_preserves_signature_file(self):
        """Verify existing uploaded signature file remains available when switching modes."""
        sample_img = create_test_image()
        self.org.signature = sample_img
        self.org.signature_mode = SignatureMode.IMAGE
        self.org.save()
        self.assertTrue(bool(self.org.signature))

        # Switch mode to authorized_signatory
        post_data = {
            "business_name": "Samruddhi Enterprises",
            "business_email": "samruddhi@example.com",
            "phone_number": "9123456789",
            "address_line_1": "456 Industrial Area",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411001",
            "country": "India",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "signature_mode": "authorized_signatory",
            "authorized_signatory_name": "Chief Financial Officer",
        }
        res = self.client.post(self.org_url, data=post_data, follow=True)
        self.assertEqual(res.status_code, 200)
        self.org.refresh_from_db()

        # Image MUST be retained
        self.assertEqual(self.org.signature_mode, "authorized_signatory")
        self.assertTrue(bool(self.org.signature))

        # Switch back to image mode without re-uploading
        post_data_back = post_data.copy()
        post_data_back["signature_mode"] = "image"
        res_back = self.client.post(self.org_url, data=post_data_back, follow=True)
        self.assertEqual(res_back.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.signature_mode, "image")
        self.assertTrue(bool(self.org.signature))

    def test_4_get_context_data_has_signature_availability(self):
        """Verify SettingsInvoiceDesignView.get_context_data() calculates has_signature correctly."""
        # Mode: none -> has_signature False
        self.org.signature_mode = SignatureMode.NONE
        self.org.save()
        res1 = self.client.get(self.design_url)
        self.assertFalse(res1.context["has_signature"])

        # Mode: authorized_signatory with name -> has_signature True
        self.org.signature_mode = SignatureMode.AUTHORIZED_SIGNATORY
        self.org.authorized_signatory_name = "Samruddhi Enterprises"
        self.org.save()
        res2 = self.client.get(self.design_url)
        self.assertTrue(res2.context["has_signature"])

        # Mode: image with signature file -> has_signature True
        self.org.signature = create_test_image()
        self.org.signature_mode = SignatureMode.IMAGE
        self.org.save()
        res3 = self.client.get(self.design_url)
        self.assertTrue(res3.context["has_signature"])

    def test_5_document_preference_show_signature_persistence(self):
        """Verify DocumentPreference.show_signature is independently persisted in Invoice Design."""
        # Ensure has_signature is True in Organization
        self.org.signature_mode = SignatureMode.AUTHORIZED_SIGNATORY
        self.org.authorized_signatory_name = "Managing Director"
        self.org.save()

        doc_pref, _ = DocumentPreference.objects.get_or_create(user=self.user)
        doc_pref.show_signature = False
        doc_pref.save()

        # POST to Invoice Design enabling signature
        post_data = {
            "template_name": doc_pref.template_name,
            "paper_size": doc_pref.paper_size,
            "orientation": doc_pref.orientation,
            "margins": doc_pref.margins,
            "font_size": doc_pref.font_size,
            "table_density": doc_pref.table_density,
            "show_signature": "on",
        }
        res = self.client.post(self.design_url, data=post_data, follow=True)
        self.assertEqual(res.status_code, 200)

        # Reload Invoice Design
        reload_res = self.client.get(self.design_url)
        doc_pref.refresh_from_db()
        self.assertTrue(doc_pref.show_signature)
        self.assertIn('name="show_signature" class="toggle-input" checked', reload_res.content.decode("utf-8"))

    def test_6_complete_end_to_end_flow(self):
        """
        Test the complete requested flow:
        Organization → select mode → Save → reload Organization → open Invoice Design → select Signature → Save → reload Invoice Design.
        """
        # Step 1: Organization → select Authorized Signatory → Save
        org_post_data = {
            "business_name": "Samruddhi Enterprises",
            "business_email": "samruddhi@example.com",
            "phone_number": "9123456789",
            "address_line_1": "456 Industrial Area",
            "city": "Pune",
            "state": "Maharashtra",
            "pincode": "411001",
            "country": "India",
            "letterhead_header_offset": 0,
            "letterhead_footer_offset": 0,
            "signature_mode": "authorized_signatory",
            "authorized_signatory_name": "Samruddhi Authorized Executive",
            "show_computer_generated_disclaimer": "True",
        }
        res_org_save = self.client.post(self.org_url, data=org_post_data, follow=True)
        self.assertEqual(res_org_save.status_code, 200)

        # Step 2: Reload Organization
        res_org_reload = self.client.get(self.org_url)
        self.assertEqual(res_org_reload.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.signature_mode, "authorized_signatory")
        self.assertEqual(self.org.authorized_signatory_name, "Samruddhi Authorized Executive")
        self.assertTrue(self.org.show_computer_generated_disclaimer)

        # Step 3: Open Invoice Design
        res_design_open = self.client.get(self.design_url)
        self.assertEqual(res_design_open.status_code, 200)
        self.assertTrue(res_design_open.context["has_signature"])

        # Step 4: Select Signature in Invoice Design → Save
        doc_pref = DocumentPreference.objects.get(user=self.user)
        design_post_data = {
            "template_name": doc_pref.template_name,
            "paper_size": doc_pref.paper_size,
            "orientation": doc_pref.orientation,
            "margins": doc_pref.margins,
            "font_size": doc_pref.font_size,
            "table_density": doc_pref.table_density,
            "show_signature": "on",
        }
        res_design_save = self.client.post(self.design_url, data=design_post_data, follow=True)
        self.assertEqual(res_design_save.status_code, 200)

        # Step 5: Reload Invoice Design
        res_design_reload = self.client.get(self.design_url)
        self.assertEqual(res_design_reload.status_code, 200)
        doc_pref.refresh_from_db()
        self.assertTrue(doc_pref.show_signature)
        self.assertTrue(res_design_reload.context["has_signature"])
        self.assertTrue(res_design_reload.context["form"]["show_signature"].value())
        self.assertIn('name="show_signature" class="toggle-input" checked', res_design_reload.content.decode("utf-8"))
