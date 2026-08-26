"""apps/billing/models.py — Invoice Models"""

import uuid
from decimal import Decimal

from django.db import models
from django.db.models import Q, UniqueConstraint
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel
from apps.organization.models import Organization
from apps.customers.models import Customer
from apps.products.models import Product


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", _("Draft")
    ISSUED = "issued", _("Issued")
    CANCELLED = "cancelled", _("Cancelled")


class EmailStatus(models.TextChoices):
    NOT_SENT = "not_sent", _("Not Sent")
    QUEUED = "queued", _("Queued")
    SENDING = "sending", _("Sending")
    SENT = "sent", _("Sent")
    FAILED = "failed", _("Failed")


class EmailTrigger(models.TextChoices):
    AUTOMATIC = "automatic", _("Automatic")
    MANUAL = "manual", _("Manual")


class DiscountType(models.TextChoices):
    PERCENTAGE = "percentage", _("Percentage")
    FIXED = "fixed", _("Fixed")
    NONE = "none", _("None")


class Invoice(TimeStampedModel):
    """
    Represents an Invoice document scoped to an Organization.
    Stores historical snapshots of customer and totals for the transaction.
    """
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="invoices",
        help_text="The organization owning this invoice."
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        related_name="invoices",
        help_text="The customer billed for this invoice."
    )
    
    invoice_number = models.CharField(max_length=50, blank=True)
    status = models.CharField(
        max_length=15,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT
    )
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    place_of_supply = models.CharField(max_length=100)

    # Customer Snapshots
    customer_name_snapshot = models.CharField(max_length=255)
    customer_gstin_snapshot = models.CharField(max_length=15, blank=True)
    customer_billing_address_snapshot = models.TextField()
    customer_state_code_snapshot = models.CharField(max_length=2)

    # Shipping Address
    shipping_same_as_billing = models.BooleanField(default=True)
    shipping_address_line_1 = models.CharField(max_length=255, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_state = models.CharField(max_length=100, blank=True)
    shipping_pincode = models.CharField(max_length=10, blank=True)

    # Totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cgst_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    sgst_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    igst_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    cess_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Other terms
    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default='INR')

    # Email Delivery Audit
    email_sent = models.BooleanField(default=False)
    email_last_sent_at = models.DateTimeField(null=True, blank=True)
    email_last_status = models.CharField(
        max_length=20,
        choices=EmailStatus.choices,
        default=EmailStatus.NOT_SENT
    )
    email_last_trigger = models.CharField(
        max_length=20,
        choices=EmailTrigger.choices,
        blank=True
    )
    email_last_error = models.TextField(blank=True)
    email_recipient = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-invoice_date", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["organization", "invoice_number"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["organization", "invoice_number"],
                condition=~Q(invoice_number=""),
                name="unique_invoice_number_per_org"
            )
        ]

    def __str__(self) -> str:
        num = self.invoice_number or "Draft"
        return f"Invoice {num} - {self.customer_name_snapshot}"


class InvoiceLine(TimeStampedModel):
    """
    Represents a line item on an Invoice.
    Stores historical snapshots of product attributes and transaction-specific values.
    """
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
        help_text="The invoice this line belongs to."
    )
    position = models.PositiveIntegerField()
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        related_name="invoice_lines",
        help_text="The product this line item refers to."
    )

    # Product Snapshots
    product_name_snapshot = models.CharField(max_length=255)
    product_type_snapshot = models.CharField(max_length=10)
    hsn_sac_snapshot = models.CharField(max_length=8, blank=True)
    taxability_type_snapshot = models.CharField(max_length=12)
    gst_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    cess_applicable_snapshot = models.BooleanField(default=False)
    cess_type_snapshot = models.CharField(max_length=14, blank=True, null=True)
    cess_rate_snapshot = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    reverse_charge_snapshot = models.BooleanField(default=False)
    price_basis_snapshot = models.CharField(max_length=10)
    uqc_snapshot = models.CharField(max_length=3)

    # Transaction values
    quantity = models.DecimalField(max_digits=10, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Discount
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.NONE
    )
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    # Calculated Totals
    taxable_value = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    cgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    sgst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    igst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    igst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    
    cess_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))

    class Meta:
        ordering = ["position"]
        indexes = [
            models.Index(fields=["invoice", "position"]),
        ]

    def clean(self):
        super().clean()
        if self.unit_price is None and self.product:
            self.unit_price = self.product.unit_price

    def save(self, *args, **kwargs):
        if self.unit_price is None and self.product:
            self.unit_price = self.product.unit_price
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.position}: {self.product_name_snapshot} on {self.invoice}"
