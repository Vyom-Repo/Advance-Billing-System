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
        return "-".join(parts)

class DocumentPreference(models.Model):
    """
    Stores default preferences for PDF layout and printing.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='document_preference')
    
    TEMPLATE_CHOICES = (
        ('gst_classic', 'GST Classic'),
        ('flipkart_invoice', 'Flipkart Invoice'),
        ('retail_gst_compact', 'Retail GST Compact'),
        ('evergreen', 'Evergreen Template'),
        ('compact_template', 'Compact Template'),
        ('genz', 'GenZ Template'),
        ('landscape_template', 'Landscape Template'),
        ('modern_template', 'Modern Template'),
        ('mrp_discount_template', 'MRP Discount Template'),
        ('professional_template', 'Professional Template'),
        ('service_template', 'Service Template'),
        ('vintage', 'Vintage Template'),
    )
    template_name = models.CharField(max_length=30, choices=TEMPLATE_CHOICES, default='gst_classic')
    
    PAPER_SIZE_CHOICES = (
        ('A4', 'A4'),
        ('Letter', 'Letter'),
    )
    paper_size = models.CharField(max_length=10, choices=PAPER_SIZE_CHOICES, default='A4')
    
    ORIENTATION_CHOICES = (
        ('Portrait', 'Portrait'),
        ('Landscape', 'Landscape'),
    )
    orientation = models.CharField(max_length=15, choices=ORIENTATION_CHOICES, default='Portrait')
    
    MARGIN_CHOICES = (
        ('Narrow', 'Narrow'),
        ('Normal', 'Normal'),
        ('Wide', 'Wide'),
    )
    margins = models.CharField(max_length=10, choices=MARGIN_CHOICES, default='Normal')
    
    show_company_logo = models.BooleanField(default=True)
    show_company_header = models.BooleanField(default=True)
    show_company_footer = models.BooleanField(default=True)
    print_on_letterhead = models.BooleanField(default=False)
    
    show_qr_code = models.BooleanField(default=True)
    show_bank_details = models.BooleanField(default=True)
    show_gst_summary = models.BooleanField(default=True)
    show_hsn_sac = models.BooleanField(default=True)
    show_signature = models.BooleanField(default=True)
    show_terms = models.BooleanField(default=True)
    show_payment_info = models.BooleanField(default=True)
    
    FONT_SIZE_CHOICES = (
        ('Small', 'Small'),
        ('Medium', 'Medium'),
        ('Large', 'Large'),
    )
    font_size = models.CharField(max_length=10, choices=FONT_SIZE_CHOICES, default='Medium')
    
    DENSITY_CHOICES = (
        ('Compact', 'Compact'),
        ('Comfortable', 'Comfortable'),
    )
    table_density = models.CharField(max_length=15, choices=DENSITY_CHOICES, default='Comfortable')
    
    show_page_numbers = models.BooleanField(default=True)
    show_print_date = models.BooleanField(default=True)
    custom_footer_message = models.TextField(blank=True, default="Thank you for your business.")

    onboarding_completed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email} Document Preferences"

