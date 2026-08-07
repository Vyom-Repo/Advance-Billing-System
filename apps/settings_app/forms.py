"""
apps/settings_app/forms.py
"""
from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()

class UserProfileForm(forms.ModelForm):
    """
    Form for updating the user's personal profile.
    """
    class Meta:
        model = User
        fields = ["first_name", "last_name"]
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})

from django.contrib.auth.forms import PasswordChangeForm

class SettingsPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-input'})

from .models import InvoicePreference

class InvoicePreferenceForm(forms.ModelForm):
    """
    Form for updating invoice preferences.
    """
    class Meta:
        model = InvoicePreference
        fields = [
            "invoice_prefix", "starting_number", "include_financial_year",
            "default_payment_terms", "custom_payment_days",
            "default_notes", "default_terms",
            "default_currency", "decimal_places", "rounding_method",
            "draft_by_default"
        ]
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            if field_name == "include_financial_year" or field_name == "draft_by_default":
                field.widget.attrs.update({'class': 'toggle-input'})
            elif field_name == "default_notes" or field_name == "default_terms":
                field.widget.attrs.update({'class': 'form-input', 'rows': 3})
            else:
                field.widget.attrs.update({'class': 'form-input'})

    def clean_invoice_prefix(self):
        prefix = self.cleaned_data.get('invoice_prefix', '')
        if prefix:
            prefix = prefix.strip().upper()
        return prefix
        
    def clean_starting_number(self):
        starting_number = self.cleaned_data.get('starting_number')
        if starting_number is not None and starting_number < 1:
            raise forms.ValidationError("Starting number must be at least 1.")
        return starting_number
        
    def clean(self):
        cleaned_data = super().clean()
        payment_terms = cleaned_data.get("default_payment_terms")
        custom_days = cleaned_data.get("custom_payment_days")
        
        if payment_terms == "Custom":
            if custom_days is None:
                self.add_error('custom_payment_days', "Please specify custom days.")
            elif custom_days < 1 or custom_days > 365:
                self.add_error('custom_payment_days', "Custom days must be between 1 and 365.")
        else:
            # If not custom, clear the custom days
            cleaned_data['custom_payment_days'] = None
            
        return cleaned_data
