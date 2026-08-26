"""
apps/settings_app/tests/test_p0_system_settings.py

Regression tests for P0-2: System Settings View Organization Display.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.organization.models import Organization

User = get_user_model()


class SystemSettingsViewP0Tests(TestCase):
    def setUp(self):
        self.user_with_org = User.objects.create_user(
            username="system_owner@example.com",
            email="system_owner@example.com",
            password="Password123!"
        )
        self.org = Organization.objects.create(
            owner=self.user_with_org,
            business_name="Enterprise Systems Ltd",
            gstin="27BBBBB1111B1Z2",
            state_code="27"
        )

        self.user_no_org = User.objects.create_user(
            username="system_noorg@example.com",
            email="system_noorg@example.com",
            password="Password123!"
        )

    def test_system_settings_with_organization(self):
        """User with organization sees business name and Active status on GET /settings/system/."""
        client = Client()
        client.force_login(self.user_with_org)
        response = client.get(reverse("settings_app:system"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["org_name"], "Enterprise Systems Ltd")
        self.assertEqual(response.context["org_status"], "Active")
        self.assertContains(response, "Enterprise Systems Ltd")

    def test_system_settings_without_organization(self):
        """User without organization sees org_name='None' and org_status='Pending Setup'."""
        client = Client()
        client.force_login(self.user_no_org)
        response = client.get(reverse("settings_app:system"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["org_name"], "None")
        self.assertEqual(response.context["org_status"], "Pending Setup")
