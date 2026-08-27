"""
apps/organization/models.py — Organization Models
"""
from django.conf import settings
from django.db import models
from apps.common.models import TimeStampedModel
from apps.common.validators import validate_image_dimensions_and_format

class SignatureMode(models.TextChoices):
    NONE = "none", "None"
    IMAGE = "image", "Signature Image"
    AUTHORIZED_SIGNATORY = "authorized_signatory", "Authorized Signatory"


class PlanTier(models.TextChoices):
    FREE = "free", "Free"
    PAID = "paid", "Advance Billing Pro"


class Organization(TimeStampedModel):
    """
    Represents the business entity using the Advance Billing platform.
    Every invoice, product, and customer will belong to an Organization.
    """
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="organization",
        help_text="The user who created and owns this organization."
    )
    
    # Business Information
    business_name = models.CharField(max_length=255)
    legal_business_name = models.CharField(max_length=255, blank=True)
    is_gst_registered = models.BooleanField(default=False)
    gstin = models.CharField(max_length=15, blank=True)
    pan = models.CharField(max_length=10, blank=True)
    state_code = models.CharField(max_length=2, blank=True)
    
    # Contact Information
    business_email = models.EmailField()
    phone_number = models.CharField(max_length=20, blank=True)
    
    # Business Address
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    country = models.CharField(max_length=100, default="India")
    
    # Branding
    logo = models.ImageField(upload_to="organization_logos/", blank=True, null=True, validators=[validate_image_dimensions_and_format])
    letterhead = models.ImageField(upload_to="organization_letterheads/", blank=True, null=True, help_text="Full A4 page background for invoices.", validators=[validate_image_dimensions_and_format])
    letterhead_header_offset = models.IntegerField(default=30, help_text="Header safe area offset in mm")
    letterhead_footer_offset = models.IntegerField(default=25, help_text="Footer safe area offset in mm")
    signature = models.ImageField(upload_to="organization_signatures/", blank=True, null=True, help_text="Authorized signatory image.", validators=[validate_image_dimensions_and_format])
    qr_code = models.ImageField(upload_to="organization_qr_codes/", blank=True, null=True, help_text="QR Code image displayed on invoices.", validators=[validate_image_dimensions_and_format])

    # Signature / Authorization & Disclaimer Settings
    signature_mode = models.CharField(
        max_length=20,
        choices=SignatureMode.choices,
        default=SignatureMode.NONE,
        help_text="Signature / Authorization mode for invoices."
    )
    authorized_signatory_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Organization / Signatory text displayed when Authorized Signatory mode is selected."
    )
    show_computer_generated_disclaimer = models.BooleanField(
        default=False,
        help_text="Show disclaimer stating invoice is computer-generated and does not require signature."
    )

    # Plan / Billing Status
    plan = models.CharField(
        max_length=10,
        choices=PlanTier.choices,
        default=PlanTier.FREE,
        help_text="Account plan: Free or Paid. Paid accounts do not receive the Advance Billing watermark on invoices."
    )

    # Terms & Conditions
    terms_and_conditions = models.TextField(blank=True, default="", help_text="Default Terms & Conditions for invoices.")

    # Demo tracking
    is_demo = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this is a temporary disposable demo organization."
    )
    demo_session_id = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Unique session ID owning this temporary demo organization."
    )

    def __str__(self) -> str:
        return self.business_name

import re
from django.core.exceptions import ValidationError

class BankAccount(TimeStampedModel):
    """
    Bank account details for an Organization.
    """
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="bank_accounts")
    bank_name = models.CharField(max_length=255)
    account_name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=50)
    ifsc_code = models.CharField(max_length=20)
    branch = models.CharField(max_length=255, blank=True)
    is_default = models.BooleanField(default=True)

    def clean(self):
        super().clean()
        if self.bank_name:
            self.bank_name = self.bank_name.strip().upper()
            
        if self.ifsc_code:
            self.ifsc_code = self.ifsc_code.strip().upper()
            if len(self.ifsc_code) != 11 or not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", self.ifsc_code):
                raise ValidationError({"ifsc_code": "IFSC must contain 4 letters, followed by 0, followed by 6 alphanumeric characters."})
                
        if self.account_number:
            self.account_number = str(self.account_number).strip()
            if not re.match(r"^\d{1,18}$", self.account_number):
                raise ValidationError({"account_number": "Account number must contain digits only (maximum 18 digits)."})

        if self.branch is not None:
            self.branch = str(self.branch).strip()
            if not self.branch:
                raise ValidationError({"branch": "Branch is required."})
        else:
            raise ValidationError({"branch": "Branch is required."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.bank_name} - {self.account_number}"

from django.db.models.signals import post_delete
from django.dispatch import receiver

@receiver(post_delete, sender=Organization)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """
    Deletes file from filesystem when corresponding `Organization` object is deleted.
    """
    if instance.logo:
        instance.logo.delete(save=False)
    if instance.letterhead:
        instance.letterhead.delete(save=False)
    if instance.signature:
        instance.signature.delete(save=False)
    if instance.qr_code:
        instance.qr_code.delete(save=False)


class RequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class UpgradeRequest(TimeStampedModel):
    """
    Tracks customer upgrade requests to remove the watermark.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="upgrade_requests"
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="upgrade_requests"
    )
    requester_name = models.CharField(max_length=255)
    requester_email = models.EmailField()
    status = models.CharField(
        max_length=20,
        choices=RequestStatus.choices,
        default=RequestStatus.PENDING,
        db_index=True
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_upgrades"
    )
    admin_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Upgrade Request"
        verbose_name_plural = "Upgrade Requests"

    def __str__(self) -> str:
        return f"{self.organization.business_name} ({self.get_status_display()})"

