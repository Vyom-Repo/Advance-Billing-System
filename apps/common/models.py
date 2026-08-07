"""
apps/common/models.py — Common Models
"""
from django.db import models

class TimeStampedModel(models.Model):
    """
    An abstract base class model that provides self-updating
    'created_at' and 'updated_at' fields.
    """
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

from django.conf import settings

class NotificationPriority(models.IntegerChoices):
    CRITICAL = 1, "Critical"
    HIGH = 2, "High"
    MEDIUM = 3, "Medium"
    LOW = 4, "Low"
    TEMPORARY = 5, "Temporary"

class NotificationCategory(models.TextChoices):
    BILLING = "billing", "Billing"
    CUSTOMERS = "customers", "Customers"
    ORGANIZATION = "organization", "Organization"
    SECURITY = "security", "Security"
    SETTINGS = "settings", "Settings"
    SYSTEM = "system", "System"

class Notification(TimeStampedModel):
    """
    Centralized notification model supporting robust scaling and value-based retention.
    """
    organization = models.ForeignKey(
        "organization.Organization",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )
    category = models.CharField(
        max_length=50,
        choices=NotificationCategory.choices
    )
    event_type = models.CharField(max_length=100)
    title = models.CharField(max_length=255)
    message = models.TextField()
    
    # Generic relations for future scalability without GenericForeignKey complexity
    entity_type = models.CharField(max_length=100, null=True, blank=True)
    entity_id = models.CharField(max_length=100, null=True, blank=True)
    
    priority = models.IntegerField(
        choices=NotificationPriority.choices,
        default=NotificationPriority.MEDIUM
    )
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', 'priority', 'created_at']),
            models.Index(fields=['organization', 'created_at']),
        ]

    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title} ({self.user.email})"
