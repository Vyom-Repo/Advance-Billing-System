"""
apps/settings_app/models.py
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.conf import settings

User = get_user_model()

class UserPreference(models.Model):
    """
    Stores user-specific preferences such as theme, language, etc.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preference')
    theme = models.CharField(max_length=50, default=settings.DEFAULT_THEME)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} Preferences"

class InvoicePreference(models.Model):
    """
    Stores default preferences for invoice creation.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='invoice_preference')
    invoice_prefix = models.CharField(max_length=15, blank=True, default="INV")
    starting_number = models.PositiveIntegerField(default=1)
    include_financial_year = models.BooleanField(default=False)
    
    PAYMENT_TERM_CHOICES = (
        ('Receipt', 'Due on Receipt'),
        ('7', '7 Days'),
        ('15', '15 Days'),
        ('30', '30 Days'),
        ('Custom', 'Custom Days'),
    )
    default_payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERM_CHOICES, default='15')
    custom_payment_days = models.PositiveIntegerField(null=True, blank=True)
    
    default_notes = models.TextField(blank=True, default="Thank you for your business.")
    default_terms = models.TextField(blank=True, default="Goods once sold will not be taken back.\nSubject to Ahmedabad jurisdiction.")
    
    CURRENCY_CHOICES = (
        ('INR', 'Indian Rupee (INR)'),
        ('USD', 'US Dollar (USD)'),
        ('EUR', 'Euro (EUR)'),
        ('GBP', 'British Pound (GBP)'),
    )
    default_currency = models.CharField(max_length=10, choices=CURRENCY_CHOICES, default="INR")
    
    DECIMAL_CHOICES = (
        (0, '0'),
        (2, '2'),
        (3, '3'),
    )
    decimal_places = models.IntegerField(default=2, choices=DECIMAL_CHOICES)
    
    ROUNDING_CHOICES = (
        ('Normal', 'Normal'),
        ('Up', 'Round Up'),
        ('Down', 'Round Down'),
    )
    rounding_method = models.CharField(max_length=10, choices=ROUNDING_CHOICES, default="Normal")
    
    draft_by_default = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} Invoice Preferences"

    def get_preview_number(self, include_fy=None):
        """
        Generate a formatted invoice number.
        This serves as the single source of truth for numbering formatting.
        """
        prefix = (self.invoice_prefix or "").strip().upper()
        
        # Determine whether to include financial year
        fy_included = self.include_financial_year
        if include_fy is not None:
            fy_included = include_fy
            
        fy_str = "2026-27" if fy_included else ""
        
        # Pad the starting number to at least 4 digits
        num_str = str(self.starting_number).zfill(4)
        
        parts = []
        if prefix:
            parts.append(prefix)
        if fy_str:
            parts.append(fy_str)
        parts.append(num_str)
        
        return "-".join(parts)
