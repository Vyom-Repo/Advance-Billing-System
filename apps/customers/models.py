"""
apps/customers/models.py — Customer Models
"""
import uuid
from django.db import models
from django.db.models import Q, UniqueConstraint
from apps.common.models import TimeStampedModel
from apps.organization.models import Organization


class CustomerType(models.TextChoices):
    BUSINESS = "business", "Business"
    INDIVIDUAL = "individual", "Individual"


class GSTStatus(models.TextChoices):
    REGISTERED = "registered", "GST Registered"
    UNREGISTERED = "unregistered", "GST Unregistered"


class Customer(TimeStampedModel):
    """
    Represents a Customer master record scoped to an Organization.
    Stores recipient identity, GST status, and structured billing address
    required for invoice generation.
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="customers",
        help_text="The organization owning this customer record."
    )
    customer_type = models.CharField(
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.BUSINESS
    )
    gst_status = models.CharField(
        max_length=20,
        choices=GSTStatus.choices,
        default=GSTStatus.REGISTERED
    )
    name = models.CharField(
        max_length=255,
        help_text="Legal Registered Name (when GST Registered) or Customer Name (when Unregistered)"
    )
    gstin = models.CharField(
        max_length=15,
        blank=True,
        help_text="15-character GSTIN format for GST Registered customers"
    )

    # Billing Address (Structured)
    billing_address_line_1 = models.CharField(max_length=255, blank=True)
    billing_address_line_2 = models.CharField(max_length=255, blank=True)
    billing_city = models.CharField(max_length=100, blank=True)
    billing_state = models.CharField(max_length=100)
    billing_state_code = models.CharField(max_length=2)
    billing_pin_code = models.CharField(max_length=10, blank=True)
    billing_country = models.CharField(max_length=100, default="India", blank=True)

    # Archiving
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "name"]),
            models.Index(fields=["organization", "gstin"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["organization", "gstin"],
                condition=Q(gst_status="registered") & ~Q(gstin=""),
                name="unique_registered_gstin_per_organization"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_gst_status_display()})"

    @property
    def is_registered(self) -> bool:
        return self.gst_status == GSTStatus.REGISTERED

    @property
    def full_billing_address(self) -> str:
        parts = [self.billing_address_line_1]
        if self.billing_address_line_2:
            parts.append(self.billing_address_line_2)
        parts.extend([
            self.billing_city,
            f"{self.billing_state} ({self.billing_state_code})",
            self.billing_pin_code,
            self.billing_country
        ])
        return ", ".join([p for p in parts if p])
