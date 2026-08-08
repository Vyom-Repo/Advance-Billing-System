"""
apps/organization/forms.py
"""
from django import forms
from .models import Organization
from .services import LocalGSTValidator

class OrganizationSetupForm(forms.ModelForm):
    """
    Form for the Organization Setup Wizard.
    """
    class Meta:
        model = Organization
        fields = [
            "business_name",
            "is_gst_registered",
            "gstin",
            "business_email",
            "phone_number",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "pincode",
            "country",
            "logo",
        ]
        
    def clean(self):
        cleaned_data = super().clean()
        is_gst_registered = cleaned_data.get("is_gst_registered")
        gstin = cleaned_data.get("gstin")
        
        if is_gst_registered:
            if not gstin:
                self.add_error("gstin", "GSTIN is required when GST Registered is Yes.")
            else:
                validation_result = LocalGSTValidator.validate(gstin)
                if not validation_result["is_valid"]:
                    self.add_error("gstin", validation_result["error"])
                else:
                    # Auto-populate extracted fields
                    cleaned_data["pan"] = validation_result["pan"]
                    cleaned_data["state_code"] = validation_result["state_code"]
        else:
            cleaned_data["gstin"] = ""
            cleaned_data["pan"] = ""
            cleaned_data["state_code"] = ""
            
        return cleaned_data


class OrganizationUpdateForm(OrganizationSetupForm):
    """
    Form for updating an existing Organization.
    Inherits setup logic and validation.
    """
    # Virtual fields for handling file removal
    remove_logo = forms.BooleanField(required=False, initial=False)
    remove_letterhead = forms.BooleanField(required=False, initial=False)
    remove_signature = forms.BooleanField(required=False, initial=False)

    class Meta(OrganizationSetupForm.Meta):
        fields = OrganizationSetupForm.Meta.fields + ["legal_business_name", "letterhead", "signature", "letterhead_header_offset", "letterhead_footer_offset"]

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('remove_logo') and instance.logo:
            instance.logo.delete(save=False)
        if self.cleaned_data.get('remove_letterhead') and instance.letterhead:
            instance.letterhead.delete(save=False)
        if self.cleaned_data.get('remove_signature') and instance.signature:
            instance.signature.delete(save=False)
        
        if commit:
            instance.save()
        return instance

from .models import BankAccount

class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ["bank_name", "account_name", "account_number", "ifsc_code", "branch"]
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})
