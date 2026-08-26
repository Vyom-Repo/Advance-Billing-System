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

    def get_target_url(self) -> str:
        """
        Safely resolves target URL based on entity_type and entity_id.
        Returns empty string if entity is missing, deleted, or unresolvable.
        """
        if not self.entity_type or not self.entity_id:
            return ""
            
        try:
            from django.urls import reverse  # noqa: PLC0415
            if self.entity_type == "invoice":
                from apps.billing.models import Invoice  # noqa: PLC0415
                if Invoice.objects.filter(uuid=self.entity_id).exists():
                    return reverse("billing:detail", kwargs={"uuid": self.entity_id})
            elif self.entity_type == "customer":
                from apps.customers.models import Customer  # noqa: PLC0415
                if Customer.objects.filter(uuid=self.entity_id).exists():
                    return reverse("customers:detail", kwargs={"uuid": self.entity_id})
            elif self.entity_type == "product":
                from apps.products.models import Product  # noqa: PLC0415
                if Product.objects.filter(uuid=self.entity_id).exists():
                    return reverse("products:detail", kwargs={"uuid": self.entity_id})
            elif self.entity_type == "organization":
                return reverse("organization:index")
        except Exception:  # noqa: BLE001
            return ""
        return ""

    def get_icon_name(self) -> str:
        icon_map = {
            "invoice_created": "file-text",
            "invoice_issued": "send",
            "invoice_cancelled": "x-circle",
            "customer_created": "user-plus",
            "product_created": "package",
            "organization_updated": "building-2",
        }
        return icon_map.get(self.event_type, "bell")

    def to_dict(self) -> dict:
        from django.utils.timesince import timesince  # noqa: PLC0415
        return {
            "id": self.id,
            "category": self.category,
            "event_type": self.event_type,
            "title": self.title,
            "message": self.message,
            "priority": self.priority,
            "is_read": self.is_read,
            "icon": self.get_icon_name(),
            "target_url": self.get_target_url(),
            "created_at": self.created_at.strftime("%b %d, %Y %H:%M"),
            "timesince": f"{timesince(self.created_at).split(',')[0]} ago",
        }
