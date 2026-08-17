"""
apps/organization/models.py — Organization Models
"""
from django.conf import settings
from django.db import models
from apps.common.models import TimeStampedModel

class SignatureMode(models.TextChoices):
    NONE = "none", "None"
    IMAGE = "image", "Signature Image"
    AUTHORIZED_SIGNATORY = "authorized_signatory", "Authorized Signatory"


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
    logo = models.ImageField(upload_to="organization_logos/", blank=True, null=True)
    letterhead = models.ImageField(upload_to="organization_letterheads/", blank=True, null=True, help_text="Full A4 page background for invoices.")
    letterhead_header_offset = models.IntegerField(default=30, help_text="Header safe area offset in mm")
    letterhead_footer_offset = models.IntegerField(default=25, help_text="Footer safe area offset in mm")
    signature = models.ImageField(upload_to="organization_signatures/", blank=True, null=True, help_text="Authorized signatory image.")
    qr_code = models.ImageField(upload_to="organization_qr_codes/", blank=True, null=True, help_text="QR Code image displayed on invoices.")

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

    # Terms & Conditions
    terms_and_conditions = models.TextField(blank=True, default="", help_text="Default Terms & Conditions for invoices.")

    def __str__(self) -> str:
        return self.business_name

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

