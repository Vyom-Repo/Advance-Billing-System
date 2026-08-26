"""
apps/common/tests/test_notifications.py

Comprehensive tests for the end-to-end Notification system in Advance Billing.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.organization.models import Organization
from apps.common.models import Notification, NotificationCategory, NotificationPriority
from apps.common.services.notification_service import NotificationService

User = get_user_model()


class NotificationSystemTests(TestCase):
    def setUp(self):
        # User & Org 1
        self.user1 = User.objects.create_user(
            username="user1@example.com",
            email="user1@example.com",
            password="Password123!",
            first_name="User",
            last_name="One"
        )
        self.org1 = Organization.objects.create(
            owner=self.user1,
            business_name="Business One",
            gstin="27AAAAA0000A1Z5"
        )
        self.user1.organization = self.org1
        self.user1.save()

        # User & Org 2 (For multi-tenant isolation testing)
        self.user2 = User.objects.create_user(
            username="user2@example.com",
            email="user2@example.com",
            password="Password123!",
            first_name="User",
            last_name="Two"
        )
        self.org2 = Organization.objects.create(
            owner=self.user2,
            business_name="Business Two",
            gstin="29BBBBB1111B2Z6"
        )
        self.user2.organization = self.org2
        self.user2.save()

        self.client1 = Client()
        self.client1.force_login(self.user1)

        self.client2 = Client()
        self.client2.force_login(self.user2)

    def test_notification_creation_and_service(self):
        """Verify NotificationService creates persistent DB records with appropriate priorities."""
        notif = NotificationService.create(
            user=self.user1,
            organization=self.org1,
            category=NotificationCategory.BILLING,
            event_type="invoice_created",
            title="Test Invoice Created",
            message="Invoice DRAFT-001 was created.",
            entity_type="invoice",
            entity_id="test-uuid"
        )
        self.assertIsNotNone(notif)
        self.assertEqual(notif.user, self.user1)
        self.assertEqual(notif.organization, self.org1)
        self.assertFalse(notif.is_read)
        self.assertEqual(Notification.objects.filter(user=self.user1).count(), 1)

    def test_notification_api_list_and_isolation(self):
        """Verify GET /api/notifications/ returns fresh DB state and isolates user notifications."""
        # Create notification for User 1
        NotificationService.create(
            user=self.user1,
            organization=self.org1,
            category=NotificationCategory.BILLING,
            event_type="invoice_created",
            title="User 1 Invoice",
            message="User 1 message"
        )

        # Create notification for User 2
        NotificationService.create(
            user=self.user2,
            organization=self.org2,
            category=NotificationCategory.CUSTOMERS,
            event_type="customer_created",
            title="User 2 Customer",
            message="User 2 message"
        )

        # User 1 fetches notifications
        res1 = self.client1.get(reverse("notification_list_api"))
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertEqual(data1["unread_count"], 1)
        self.assertEqual(len(data1["notifications"]), 1)
        self.assertEqual(data1["notifications"][0]["title"], "User 1 Invoice")

        # User 2 fetches notifications
        res2 = self.client2.get(reverse("notification_list_api"))
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2["unread_count"], 1)
        self.assertEqual(data2["notifications"][0]["title"], "User 2 Customer")

    def test_mark_individual_notification_read(self):
        """Verify POST /api/notifications/<id>/read/ marks notification read securely."""
        notif1 = NotificationService.create(
            user=self.user1,
            organization=self.org1,
            category=NotificationCategory.BILLING,
            event_type="invoice_issued",
            title="Invoice Issued",
            message="Issued invoice INV-001"
        )

        # User 2 attempts to mark User 1's notification as read -> must fail 404
        res_fail = self.client2.post(reverse("notification_mark_read_api", kwargs={"pk": notif1.pk}))
        self.assertEqual(res_fail.status_code, 404)
        notif1.refresh_from_db()
        self.assertFalse(notif1.is_read)

        # User 1 marks own notification as read -> must succeed 200
        res_ok = self.client1.post(reverse("notification_mark_read_api", kwargs={"pk": notif1.pk}))
        self.assertEqual(res_ok.status_code, 200)
        notif1.refresh_from_db()
        self.assertTrue(notif1.is_read)
        self.assertEqual(res_ok.json()["unread_count"], 0)

    def test_mark_all_notifications_read(self):
        """Verify POST /api/notifications/read-all/ marks all user notifications read."""
        for i in range(3):
            NotificationService.create(
                user=self.user1,
                organization=self.org1,
                category=NotificationCategory.BILLING,
                event_type="invoice_created",
                title=f"Invoice {i}",
                message=f"Message {i}"
            )

        self.assertEqual(Notification.objects.filter(user=self.user1, is_read=False).count(), 3)
        res = self.client1.post(reverse("notification_mark_all_read_api"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["unread_count"], 0)
        self.assertEqual(Notification.objects.filter(user=self.user1, is_read=False).count(), 0)

    def test_deleted_entity_target_url_resilience(self):
        """Verify target URL resolution handles missing/deleted objects without crashing."""
        notif = NotificationService.create(
            user=self.user1,
            organization=self.org1,
            category=NotificationCategory.BILLING,
            event_type="invoice_created",
            title="Deleted Invoice",
            message="Invoice was deleted",
            entity_type="invoice",
            entity_id="non-existent-uuid"
        )
        self.assertEqual(notif.get_target_url(), "")
        self.assertIn("target_url", notif.to_dict())
        self.assertEqual(notif.to_dict()["target_url"], "")
