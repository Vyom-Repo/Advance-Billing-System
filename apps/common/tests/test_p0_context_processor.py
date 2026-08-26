"""
apps/common/tests/test_p0_context_processor.py

Regression tests for P0-1: Global Context Processor Organization Lookup & Notification Count.
"""
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from apps.organization.models import Organization
from apps.common.models import Notification, NotificationCategory, NotificationPriority
from apps.common.context_processors import app_context

User = get_user_model()


class GlobalContextProcessorP0Tests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

        # User 1 with Organization
        self.user_with_org = User.objects.create_user(
            username="owner@example.com",
            email="owner@example.com",
            password="Password123!"
        )
        self.org = Organization.objects.create(
            owner=self.user_with_org,
            business_name="Acme Billing Corp",
            gstin="27AAAAA0000A1Z5",
            state_code="27"
        )

        # Create 2 unread notifications for user_with_org
        Notification.objects.create(
            user=self.user_with_org,
            organization=self.org,
            category=NotificationCategory.BILLING,
            event_type="invoice_created",
            title="Invoice Created",
            message="Test invoice created",
            priority=NotificationPriority.MEDIUM,
            is_read=False
        )
        Notification.objects.create(
            user=self.user_with_org,
            organization=self.org,
            category=NotificationCategory.SYSTEM,
            event_type="system_update",
            title="System Alert",
            message="System update available",
            priority=NotificationPriority.HIGH,
            is_read=False
        )

        # User 2 without Organization
        self.user_no_org = User.objects.create_user(
            username="noorg@example.com",
            email="noorg@example.com",
            password="Password123!"
        )

    def test_authenticated_user_with_organization_context(self):
        """Authenticated user with an organization receives user_org and unread notification count."""
        request = self.factory.get("/")
        request.user = self.user_with_org

        context = app_context(request)
        self.assertEqual(context["user_org"], self.org)
        self.assertEqual(context["user_org"].business_name, "Acme Billing Corp")
        self.assertEqual(context["unread_notifications_count"], 2)

    def test_authenticated_user_without_organization_context(self):
        """Authenticated user without an organization receives user_org=None and count=0."""
        request = self.factory.get("/")
        request.user = self.user_no_org

        context = app_context(request)
        self.assertIsNone(context["user_org"])
        self.assertEqual(context["unread_notifications_count"], 0)

    def test_anonymous_user_context(self):
        """Anonymous user receives user_org=None and count=0."""
        request = self.factory.get("/")
        request.user = AnonymousUser()

        context = app_context(request)
        self.assertIsNone(context["user_org"])
        self.assertEqual(context["unread_notifications_count"], 0)
