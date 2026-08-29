"""
apps/organization/forms.py
"""
from django import forms
from django.core.files.uploadedfile import UploadedFile
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

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        if isinstance(logo, UploadedFile):
            from apps.common.validators import validate_image_dimensions_and_format  # noqa: PLC0415
            validate_image_dimensions_and_format(logo)
        return logo


class OrganizationUpdateForm(OrganizationSetupForm):
    """
    Form for updating an existing Organization.
    Inherits setup logic and validation.
    """
    # Virtual fields for handling file removal
    remove_logo = forms.BooleanField(required=False, initial=False)
    remove_letterhead = forms.BooleanField(required=False, initial=False)
    remove_signature = forms.BooleanField(required=False, initial=False)
    remove_qr_code = forms.BooleanField(required=False, initial=False)

    class Meta(OrganizationSetupForm.Meta):
        fields = OrganizationSetupForm.Meta.fields + [
            "legal_business_name", "letterhead", "signature", "qr_code",
            "letterhead_header_offset", "letterhead_footer_offset",
            "signature_mode", "authorized_signatory_name", "show_computer_generated_disclaimer",
            "terms_and_conditions",
        ]

    def clean(self):
        cleaned_data = super().clean()
        sig_mode = cleaned_data.get("signature_mode") or "none"
        
        # Trim authorized_signatory_name
        auth_name = (cleaned_data.get("authorized_signatory_name") or "").strip()
        cleaned_data["authorized_signatory_name"] = auth_name

        if sig_mode == "authorized_signatory":
            if not auth_name:
                self.add_error(
                    "authorized_signatory_name",
                    "Authorized Signatory Name is required when Authorized Signatory mode is selected."
                )
        elif sig_mode == "image":
            has_existing_signature = bool(self.instance and self.instance.signature)
            is_removing = bool(cleaned_data.get("remove_signature"))
            has_new_upload = bool(self.files and self.files.get("signature"))

            if is_removing or not (has_existing_signature or has_new_upload):
                self.add_error(
                    "signature_mode",
                    "A valid signature image must be uploaded or already present when Signature Image mode is selected."
                )

        return cleaned_data

    def clean_letterhead(self):
        letterhead = self.cleaned_data.get("letterhead")
        if isinstance(letterhead, UploadedFile):
            from apps.common.validators import validate_image_dimensions_and_format  # noqa: PLC0415
            validate_image_dimensions_and_format(letterhead)
        return letterhead

    def clean_signature(self):
        signature = self.cleaned_data.get("signature")
        if isinstance(signature, UploadedFile):
            from apps.common.validators import validate_image_dimensions_and_format  # noqa: PLC0415
            validate_image_dimensions_and_format(signature)
        return signature

    def clean_qr_code(self):
        qr_code = self.cleaned_data.get("qr_code")
        if isinstance(qr_code, UploadedFile):
            from apps.common.validators import validate_image_dimensions_and_format  # noqa: PLC0415
            validate_image_dimensions_and_format(qr_code)
        return qr_code

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.cleaned_data.get('remove_logo') and instance.logo:
            instance.logo.delete(save=False)
        if self.cleaned_data.get('remove_letterhead') and instance.letterhead:
            instance.letterhead.delete(save=False)
        if self.cleaned_data.get('remove_signature') and instance.signature:
            instance.signature.delete(save=False)
        if self.cleaned_data.get('remove_qr_code') and instance.qr_code:
            instance.qr_code.delete(save=False)
        
        if commit:
            instance.save()
        return instance

import re
from .models import BankAccount

class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ["bank_name", "account_name", "account_number", "ifsc_code", "branch"]
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['branch'].required = True
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control'})

    def clean_bank_name(self):
        bank_name = (self.cleaned_data.get("bank_name") or "").strip()
        if not bank_name:
            raise forms.ValidationError("Bank Name is required.")
        return bank_name.upper()

    def clean_account_number(self):
        account_number = str(self.cleaned_data.get("account_number") or "").strip()
        if not account_number:
            raise forms.ValidationError("Account Number is required.")
        if not account_number.isdigit():
            raise forms.ValidationError("Account number must contain digits only.")
        if len(account_number) > 18:
            raise forms.ValidationError("Account number cannot exceed 18 digits.")
        if len(account_number) < 1:
            raise forms.ValidationError("Account number cannot be empty.")
        return account_number

    def clean_ifsc_code(self):
        ifsc_code = (self.cleaned_data.get("ifsc_code") or "").strip().upper()
        if not ifsc_code:
            raise forms.ValidationError("IFSC Code is required.")
        if len(ifsc_code) != 11:
            raise forms.ValidationError("Enter a valid 11-character IFSC code.")
        if not re.match(r"^[A-Z]{4}0[A-Z0-9]{6}$", ifsc_code):
            raise forms.ValidationError("IFSC must contain 4 letters, followed by 0, followed by 6 alphanumeric characters.")
        return ifsc_code

    def clean_branch(self):
        branch = (self.cleaned_data.get("branch") or "").strip()
        if not branch:
            raise forms.ValidationError("Branch is required.")
        return branch
