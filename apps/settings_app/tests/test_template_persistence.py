"""
apps/settings_app/tests/test_template_persistence.py

End-to-end integration tests for invoice template selection persistence.

Verifies:
1. Browser-like HTTP POST to SettingsInvoiceDesignView saves template_name to DocumentPreference.
2. HTTP GET after save returns selected template in context and HTML form.
3. Reloading page or navigating away & returning retains the selected template (professional_template, compact_template, vintage).
4. Updating other Invoice Design settings (e.g. show_gst_summary, show_qr_code) does not reset or mutate template_name.
5. InvoicePreviewService resolves explicit preview overrides without mutating persisted DB preference.
6. InvoicePreviewService resolves saved user preference when no explicit template override is passed.
7. Existing user preferences (e.g. vintage, compact_template) are protected and never overwritten by defaults.
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.settings_app.models import DocumentPreference, BillTemplate
from apps.invoices.services.invoice_preview_service import InvoicePreviewService

User = get_user_model()


class TemplatePersistenceTestCase(TestCase):
    """
    Tests complete template persistence pipeline from HTTP POST form submission to DB,
    GET rendering, PDF resolution, and preference protection.
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="persistuser",
            email="persist@example.com",
            password="testpassword123",
            first_name="Persist",
            last_name="User",
        )
        self.client = Client()
        self.client.login(username="persistuser", password="testpassword123")

        # Seed official bill templates
        from django.core.management import call_command
        call_command("seed_bill_templates", verbosity=0)

        self.url = reverse("settings_app:invoice_design")

    def test_post_professional_template_persistence(self):
        """1. POST professional_template -> DB updated -> GET returns Professional."""
        response = self.client.post(self.url, {
            "template_name": "professional_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "show_company_logo": "on",
            "show_company_header": "on",
        }, follow=True)

        self.assertEqual(response.status_code, 200)

        doc_pref = DocumentPreference.objects.get(user=self.user)
        self.assertEqual(doc_pref.template_name, "professional_template")

        # Context active title check
        self.assertEqual(response.context["active_template_title"], "Professional")

        # HTML form check
        html = response.content.decode("utf-8")
        self.assertIn('value="professional_template" selected', html)

    def test_post_compact_template_persistence(self):
        """2. POST compact_template -> DB updated -> GET returns Compact."""
        response = self.client.post(self.url, {
            "template_name": "compact_template",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Small",
            "table_density": "Compact",
        }, follow=True)

        self.assertEqual(response.status_code, 200)

        doc_pref = DocumentPreference.objects.get(user=self.user)
        self.assertEqual(doc_pref.template_name, "compact_template")
        self.assertEqual(response.context["active_template_title"], "Compact")

        html = response.content.decode("utf-8")
        self.assertIn('value="compact_template" selected', html)

    def test_post_vintage_template_persistence(self):
        """3. POST vintage -> DB updated -> GET returns Vintage."""
        response = self.client.post(self.url, {
            "template_name": "vintage",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Small",
            "table_density": "Compact",
        }, follow=True)

        self.assertEqual(response.status_code, 200)

        doc_pref = DocumentPreference.objects.get(user=self.user)
        self.assertEqual(doc_pref.template_name, "vintage")
        self.assertEqual(response.context["active_template_title"], "Vintage")

        html = response.content.decode("utf-8")
        self.assertIn('value="vintage" selected', html)

    def test_navigation_and_reload_persistence(self):
        """4. Verify saved selection survives page reload and navigation away/back."""
        # Set to vintage
        doc_pref, _ = DocumentPreference.objects.get_or_create(user=self.user)
        doc_pref.template_name = "vintage"
        doc_pref.save()

        # Simulate browser refresh / GET request
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_template_title"], "Vintage")

        # Simulate returning after navigating to profile
        profile_url = reverse("settings_app:profile")
        self.client.get(profile_url)
        response_return = self.client.get(self.url)
        self.assertEqual(response_return.status_code, 200)
        self.assertEqual(response_return.context["active_template_title"], "Vintage")

    def test_saving_other_settings_preserves_template_name(self):
        """5. Saving other settings (e.g., GST summary, QR) does not mutate template_name."""
        # Save initial preference as vintage
        doc_pref, _ = DocumentPreference.objects.get_or_create(user=self.user)
        doc_pref.template_name = "vintage"
        doc_pref.save()

        # POST form with vintage and toggled checkboxes
        response = self.client.post(self.url, {
            "template_name": "vintage",
            "paper_size": "A4",
            "orientation": "Portrait",
            "margins": "Normal",
            "font_size": "Medium",
            "table_density": "Comfortable",
            "show_gst_summary": "on",
            "show_qr_code": "on",
            "show_bank_details": "on",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        doc_pref.refresh_from_db()
        self.assertEqual(doc_pref.template_name, "vintage")
        self.assertTrue(doc_pref.show_gst_summary)

    def test_preview_without_explicit_template_uses_saved_preference(self):
        """6. Preview request without template_name uses user's saved preference."""
        doc_pref, _ = DocumentPreference.objects.get_or_create(user=self.user)
        doc_pref.template_name = "vintage"
        doc_pref.save()

        config = InvoicePreviewService.resolve_render_config(user=self.user)
        self.assertEqual(config.get("template_name"), "vintage")

    def test_explicit_preview_override_does_not_mutate_db(self):
        """7. Explicit preview override uses requested template without mutating DB."""
        doc_pref, _ = DocumentPreference.objects.get_or_create(user=self.user)
        doc_pref.template_name = "vintage"
        doc_pref.save()

        # Explicit preview override request for professional_template
        config = InvoicePreviewService.resolve_render_config(
            template_slug="professional_template",
            user=self.user,
            request_overrides={"template_name": "professional_template"}
        )
        self.assertEqual(config.get("template_name"), "professional_template")

        # Database remains vintage
        doc_pref.refresh_from_db()
        self.assertEqual(doc_pref.template_name, "vintage")

    def test_existing_preference_protection(self):
        """8. Pre-existing saved preferences (compact_template, vintage) are never overwritten by defaults."""
        doc_pref, _ = DocumentPreference.objects.get_or_create(user=self.user)
        doc_pref.template_name = "compact_template"
        doc_pref.save()

        response = self.client.get(self.url)
        self.assertEqual(response.context["active_template_title"], "Compact")

        doc_pref.refresh_from_db()
        self.assertEqual(doc_pref.template_name, "compact_template")
