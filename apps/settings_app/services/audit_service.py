"""
apps/settings_app/services/audit_service.py

Service for recording DataManagementAuditLog entries and surfacing system notifications.
"""

import logging
from typing import Any, Dict, Optional
from django.contrib.auth import get_user_model
from apps.common.models import Notification, NotificationCategory, NotificationPriority
from apps.organization.models import Organization
from apps.settings_app.models import DataManagementAuditLog

User = get_user_model()
logger = logging.getLogger(__name__)


class DataManagementAuditService:
    @classmethod
    def log_action(
        cls,
        organization: Organization,
        user: Optional[User],
        action: str,
        details: Optional[Dict[str, Any]] = None,
        status: str = "success",
        request: Optional[Any] = None,
        notify_user: bool = True,
        notification_title: str = "",
        notification_message: str = "",
    ) -> DataManagementAuditLog:
        """
        Creates an audit log entry and optionally creates an in-app notification.
        """
        ip_address = None
        if request:
            x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
            if x_forwarded_for:
                ip_address = x_forwarded_for.split(",")[0].strip()
            else:
                ip_address = request.META.get("REMOTE_ADDR")

        audit_log = DataManagementAuditLog.objects.create(
            organization=organization,
            user=user,
            action=action,
            status=status,
            details=details or {},
            ip_address=ip_address,
        )

        # Notify organization owner if required
        if notify_user and notification_title and notification_message:
            target_user = user or getattr(organization, "owner", None)
            if target_user:
                priority = NotificationPriority.HIGH if status != "success" else NotificationPriority.MEDIUM
                Notification.objects.create(
                    organization=organization,
                    user=target_user,
                    category=NotificationCategory.SETTINGS,
                    event_type=f"data_mgmt_{action}",
                    title=notification_title,
                    message=notification_message,
                    priority=priority,
                )

        return audit_log
