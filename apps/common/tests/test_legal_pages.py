"""
apps/common/tests/test_legal_pages.py

Unit tests for public Privacy Policy and Terms of Service pages.
"""

from django.test import TestCase
from django.urls import reverse


class LegalPagesTests(TestCase):
    def test_privacy_policy_accessible_unauthenticated(self):
        url = reverse("privacy_policy")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Privacy Policy")
        self.assertContains(response, "Digital Personal Data Protection Act, 2023")
        self.assertContains(response, "Digital Personal Data Protection Rules, 2025")
        self.assertContains(response, "Table of Contents")
        self.assertContains(response, "Data Processing Matrix")
        self.assertContains(response, "font-style: italic !important;")
        self.assertContains(response, "Vyom Prajapati")
        self.assertContains(response, "https://www.linkedin.com/in/vyom-prajapati-25209936a/")

    def test_terms_of_service_accessible_unauthenticated(self):
        url = reverse("terms_of_service")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Terms of Service")
        self.assertContains(response, "Limitation of Liability")
        self.assertContains(response, "font-style: italic !important;")
        self.assertContains(response, "Vyom Prajapati")
        self.assertContains(response, reverse("privacy_policy"))
        self.assertContains(response, reverse("terms_of_service"))

    def test_landing_page_links_to_legal_pages_and_linkedin(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("privacy_policy"))
        self.assertContains(response, reverse("terms_of_service"))
        self.assertContains(response, "Created by")
        self.assertContains(response, "https://www.linkedin.com/in/vyom-prajapati-25209936a/")
