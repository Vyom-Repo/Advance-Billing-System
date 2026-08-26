"""
apps/settings_app/tests/test_branding_toggles.py

Tests end-to-end functionality for the Invoice Design Branding toggles:
1. Company Logo toggle (OFF <-> ON, save, refresh persistence).
2. Company Header toggle (OFF <-> ON, save, refresh persistence).
3. Company Footer toggle (OFF <-> ON, save, refresh persistence).
4. Independent toggle state persistence.
5. Letterhead Mode interaction: when print_on_letterhead is enabled, branding controls clean to False.
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.settings_app.models import DocumentPreference

User = get_user_model()


class BrandingTogglesTestCase(TestCase):
    """
    Tests complete persistence and independence of Company Logo, Header, and Footer toggles.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="brandinguser",
            email="branding@example.com",
            password="testpassword123",
            first_name="Branding",
            last_name="User",
        )
        self.client = Client()
        self.client.login(username="brandinguser", password="testpassword123")
        self.url = reverse("settings_app:invoice_design")

    def test_company_logo_toggle_persistence(self):
        """1. Turn Company Logo OFF -> save -> refresh -> verifies OFF. Turn ON -> save -> refresh -> ON."""
        # Turn OFF
        response = self.client.post(self.url, {
            "template_name": "professional_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "show_company_header": "on",
            "show_company_footer": "on",
            # show_company_logo omitted (OFF)
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        doc_pref = DocumentPreference.objects.get(user=self.user)
        self.assertFalse(doc_pref.show_company_logo)

        # GET request after refresh
        get_res = self.client.get(self.url)
        self.assertFalse(get_res.context["form"]["show_company_logo"].value())

        # Turn ON
        response_on = self.client.post(self.url, {
            "template_name": "professional_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "show_company_logo": "on",
            "show_company_header": "on",
            "show_company_footer": "on",
        }, follow=True)

        self.assertEqual(response_on.status_code, 200)
        doc_pref.refresh_from_db()
        self.assertTrue(doc_pref.show_company_logo)

    def test_company_header_toggle_persistence(self):
        """2. Turn Company Header OFF -> save -> refresh -> verifies OFF. Turn ON -> save -> refresh -> ON."""
        # Turn OFF
        self.client.post(self.url, {
            "template_name": "professional_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "show_company_logo": "on",
            "show_company_footer": "on",
            # show_company_header omitted
        }, follow=True)

        doc_pref = DocumentPreference.objects.get(user=self.user)
        self.assertFalse(doc_pref.show_company_header)

        # Turn ON
        self.client.post(self.url, {
            "template_name": "professional_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "show_company_logo": "on",
            "show_company_header": "on",
            "show_company_footer": "on",
        }, follow=True)

        doc_pref.refresh_from_db()
        self.assertTrue(doc_pref.show_company_header)

    def test_company_footer_toggle_persistence(self):
        """3. Turn Company Footer OFF -> save -> refresh -> verifies OFF. Turn ON -> save -> refresh -> ON."""
        # Turn OFF
        self.client.post(self.url, {
            "template_name": "professional_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "show_company_logo": "on",
            "show_company_header": "on",
            # show_company_footer omitted
        }, follow=True)

        doc_pref = DocumentPreference.objects.get(user=self.user)
        self.assertFalse(doc_pref.show_company_footer)

        # Turn ON
        self.client.post(self.url, {
            "template_name": "professional_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "show_company_logo": "on",
            "show_company_header": "on",
            "show_company_footer": "on",
        }, follow=True)

        doc_pref.refresh_from_db()
        self.assertTrue(doc_pref.show_company_footer)

    def test_toggles_remain_independent(self):
        """4. Verify each branding toggle can be set independently without affecting others."""
        # Logo ON, Header OFF, Footer ON
        self.client.post(self.url, {
            "template_name": "professional_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "show_company_logo": "on",
            "show_company_footer": "on",
        }, follow=True)

        doc_pref = DocumentPreference.objects.get(user=self.user)
        self.assertTrue(doc_pref.show_company_logo)
        self.assertFalse(doc_pref.show_company_header)
        self.assertTrue(doc_pref.show_company_footer)

    def test_letterhead_mode_disables_branding(self):
        """5. When print_on_letterhead is enabled, form cleaning sets logo, header, and footer to False."""
        self.client.post(self.url, {
            "template_name": "professional_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "print_on_letterhead": "on",
            "show_company_logo": "on",
            "show_company_header": "on",
            "show_company_footer": "on",
        }, follow=True)

        doc_pref = DocumentPreference.objects.get(user=self.user)
        self.assertTrue(doc_pref.print_on_letterhead)
        self.assertFalse(doc_pref.show_company_logo)
        self.assertFalse(doc_pref.show_company_header)
        self.assertFalse(doc_pref.show_company_footer)
