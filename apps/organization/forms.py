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
    class Meta(OrganizationSetupForm.Meta):
        fields = OrganizationSetupForm.Meta.fields + ["legal_business_name"]
