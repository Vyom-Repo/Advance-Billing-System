"""
apps/common/urls.py — Utility URLs (health check, etc.)
"""

from django.urls import path
from .views import (
    HealthCheckView,
    NotificationListView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
    NotificationDeleteView,
)

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health_check"),
    path("api/notifications/", NotificationListView.as_view(), name="notification_list_api"),
    path("api/notifications/<int:pk>/read/", NotificationMarkReadView.as_view(), name="notification_mark_read_api"),
    path("api/notifications/read-all/", NotificationMarkAllReadView.as_view(), name="notification_mark_all_read_api"),
    path("api/notifications/<int:pk>/delete/", NotificationDeleteView.as_view(), name="notification_delete_api"),
]
