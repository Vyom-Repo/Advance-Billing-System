"""
apps/organization/models.py — Organization Models
"""
from django.conf import settings
from django.db import models
from apps.common.models import TimeStampedModel

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

    def __str__(self) -> str:
        return self.business_name

from django.db.models.signals import post_delete
from django.dispatch import receiver

@receiver(post_delete, sender=Organization)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """
    Deletes file from filesystem when corresponding `Organization` object is deleted.
    """
    if instance.logo:
        instance.logo.delete(save=False)
