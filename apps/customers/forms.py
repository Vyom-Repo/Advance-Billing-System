"""
apps/customers/forms.py — Customer Forms
"""
import re
from django import forms
from apps.organization.services import LocalGSTValidator
from .models import Customer, CustomerType, GSTStatus


class CustomerForm(forms.ModelForm):
    """
    Form for creating and updating Customer master records.
    Enforces local GSTIN format validation, state code consistency,
    Indian PIN code format, and organization-level duplicate prevention.
    """
    STATE_CHOICES = [("", "Select State")] + [
        (code, f"{name} ({code})") for code, name in sorted(LocalGSTValidator.STATE_CODES.items(), key=lambda x: x[1])
    ]

    state_select = forms.ChoiceField(
        choices=STATE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_state_select"})
    )

    class Meta:
        model = Customer
        fields = [
            "customer_type",
            "gst_status",
            "name",
            "gstin",
            "billing_address_line_1",
            "billing_address_line_2",
            "billing_city",
            "billing_state",
            "billing_state_code",
            "billing_pin_code",
            "billing_country",
        ]
        widgets = {
            "customer_type": forms.HiddenInput(attrs={"id": "id_customer_type"}),
            "gst_status": forms.HiddenInput(attrs={"id": "id_gst_status"}),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Enter customer or legal registered name", "id": "id_name"}),
            "gstin": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 24AABCT1332L1Z9", "maxlength": "15", "id": "id_gstin", "style": "text-transform: uppercase;"}),
            "billing_address_line_1": forms.TextInput(attrs={"class": "form-control", "placeholder": "Street address, building, suite", "id": "id_billing_address_line_1"}),
            "billing_address_line_2": forms.TextInput(attrs={"class": "form-control", "placeholder": "Apartment, landmark, area (optional)", "id": "id_billing_address_line_2"}),
            "billing_city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City or town", "id": "id_billing_city"}),
            "billing_state": forms.HiddenInput(attrs={"id": "id_billing_state"}),
            "billing_state_code": forms.HiddenInput(attrs={"id": "id_billing_state_code"}),
            "billing_pin_code": forms.TextInput(attrs={"class": "form-control", "placeholder": "6-digit PIN code", "maxlength": "6", "id": "id_billing_pin_code"}),
            "billing_country": forms.TextInput(attrs={"class": "form-control", "default": "India", "id": "id_billing_country"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

        if not self.initial.get("billing_country"):
            self.fields["billing_country"].initial = "India"
        if not self.initial.get("customer_type"):
            self.fields["customer_type"].initial = CustomerType.BUSINESS
        if not self.initial.get("gst_status"):
            self.fields["gst_status"].initial = GSTStatus.REGISTERED

        if self.instance and self.instance.billing_state_code:
            self.fields["state_select"].initial = self.instance.billing_state_code

    def clean_gstin(self):
        gstin = self.cleaned_data.get("gstin", "").strip().upper()
        gst_status = self.cleaned_data.get("gst_status") or self.data.get("gst_status")

        if gst_status == GSTStatus.REGISTERED:
            if not gstin:
                raise forms.ValidationError("GSTIN is required for a GST Registered customer.")
            
            res = LocalGSTValidator.validate(gstin)
            if not res["is_valid"]:
                raise forms.ValidationError(res.get("error", "Invalid GSTIN format."))
            
            return gstin
        else:
            return ""

    def clean_billing_pin_code(self):
        pin = self.cleaned_data.get("billing_pin_code", "").strip()
        country = self.cleaned_data.get("billing_country", "India").strip()

        if country.lower() == "india":
            if not re.match(r"^\d{6}$", pin):
                raise forms.ValidationError("PIN code must be exactly 6 numeric digits for India.")
        return pin

    def clean(self):
        cleaned_data = super().clean()
        gst_status = cleaned_data.get("gst_status")
        gstin = cleaned_data.get("gstin", "").strip().upper()
        name = cleaned_data.get("name", "").strip()
        billing_state = cleaned_data.get("billing_state", "").strip()
        billing_state_code = cleaned_data.get("billing_state_code", "").strip()

        if not name:
            label = "Legal Registered Name" if gst_status == GSTStatus.REGISTERED else "Customer Name"
            self.add_error("name", f"{label} is required.")

        # Ensure state and state_code are populated
        state_select_code = self.data.get("state_select", "").strip()
        if state_select_code and state_select_code in LocalGSTValidator.STATE_CODES:
            cleaned_data["billing_state_code"] = state_select_code
            cleaned_data["billing_state"] = LocalGSTValidator.STATE_CODES[state_select_code]
            billing_state_code = state_select_code
            billing_state = LocalGSTValidator.STATE_CODES[state_select_code]

        if not billing_state or not billing_state_code:
            self.add_error("billing_state", "Please select a valid State.")

        # Duplicate check for registered customers in the organization
        if gst_status == GSTStatus.REGISTERED and gstin and self.organization:
            qs = Customer.objects.filter(
                organization=self.organization,
                gstin=gstin,
                gst_status=GSTStatus.REGISTERED
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            
            if qs.exists():
                existing = qs.first()
                self.add_error("gstin", f"A registered customer with GSTIN {gstin} ({existing.name}) already exists in your organization.")

        return cleaned_data
