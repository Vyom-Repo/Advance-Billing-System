"""
apps/products/forms.py — Product Forms

Validates the full Product V1 field set.
Backend validation mirrors the frontend JS conditional rules so that
the form is secure even without JavaScript.
"""
import re
from decimal import Decimal

from django import forms

from .models import Product, ProductType, TaxabilityType, PriceBasis, CessType
from .gst_config import (
    GST_RATE_CHOICES,
    VALID_GST_RATE_VALUES,
    GST_RATE_DEFAULT,
    UQC_CHOICES,
    VALID_UQC_VALUES,
)


class ProductForm(forms.ModelForm):
    """
    Form for creating and updating Product master records.

    Conditional validation rules (enforced server-side):
      - Goods   → hsn_code required; sac_code ignored
      - Service → sac_code required; hsn_code ignored
      - Taxable → gst_rate required from approved list
      - Exempt / Nil-rated / Non-GST → gst_rate not required as tax amount
      - cess_applicable=True → cess_type + cess_rate_or_amount required
      - Goods   → uqc required from controlled list
      - Service → uqc must still be a controlled value if provided

    Organization is never accepted from POST data; it is injected by the view.
    """

    # GST Rate as a choice field so only configured values are selectable
    gst_rate = forms.ChoiceField(
        choices=[("", "Select GST Rate")] + GST_RATE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_gst_rate"}),
        label="GST Rate",
    )

    # UQC as a choice field so only controlled codes are selectable
    uqc = forms.ChoiceField(
        choices=UQC_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "id_uqc"}),
        label="Unit / UQC",
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "product_type",
            "hsn_code",
            "sac_code",
            "taxability_type",
            "gst_rate",
            "cess_applicable",
            "cess_type",
            "cess_rate_or_amount",
            "reverse_charge_applicable",
            "unit_price",
            "price_basis",
            "uqc",
        ]
        widgets = {
            # product_type is driven by radio cards; store as hidden
            "product_type": forms.HiddenInput(attrs={"id": "id_product_type"}),
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. Web Development Services, Steel Rods 10mm",
                "id": "id_name",
            }),
            "hsn_code": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 7214 or 721410",
                "maxlength": "8",
                "id": "id_hsn_code",
                "inputmode": "numeric",
            }),
            "sac_code": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 998313",
                "maxlength": "6",
                "id": "id_sac_code",
                "inputmode": "numeric",
            }),
            "taxability_type": forms.Select(attrs={
                "class": "form-select",
                "id": "id_taxability_type",
            }),
            "cess_applicable": forms.HiddenInput(attrs={"id": "id_cess_applicable"}),
            "cess_type": forms.Select(attrs={
                "class": "form-select",
                "id": "id_cess_type",
            }),
            "cess_rate_or_amount": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. 5.00",
                "step": "0.0001",
                "id": "id_cess_rate_or_amount",
            }),
            "reverse_charge_applicable": forms.HiddenInput(attrs={"id": "id_reverse_charge_applicable"}),
            "unit_price": forms.NumberInput(attrs={
                "class": "form-control",
                "placeholder": "0.00",
                "step": "0.01",
                "min": "0.01",
                "id": "id_unit_price",
            }),
            "price_basis": forms.HiddenInput(attrs={"id": "id_price_basis"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

        # Pre-populate choice fields from existing instance
        if self.instance and self.instance.pk:
            rate_str = str(self.instance.gst_rate) if self.instance.gst_rate is not None else GST_RATE_DEFAULT
            # Format to 2 decimal places to match choice keys
            try:
                rate_str = f"{Decimal(rate_str):.2f}"
            except Exception:
                rate_str = GST_RATE_DEFAULT
            self.fields["gst_rate"].initial = rate_str
            self.fields["uqc"].initial = self.instance.uqc

        # Defaults for new forms
        if not self.instance or not self.instance.pk:
            self.fields["gst_rate"].initial = GST_RATE_DEFAULT

    # ------------------------------------------------------------------
    # Field-level validation
    # ------------------------------------------------------------------

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise forms.ValidationError("Product / Service Name is required.")
        return name

    def clean_hsn_code(self):
        code = self.cleaned_data.get("hsn_code", "").strip()
        if code and not re.match(r"^\d{2,8}$", code):
            raise forms.ValidationError(
                "HSN Code must be 2–8 numeric digits (e.g. 72 or 721410)."
            )
        return code

    def clean_sac_code(self):
        code = self.cleaned_data.get("sac_code", "").strip()
        if code and not re.match(r"^\d{4,6}$", code):
            raise forms.ValidationError(
                "SAC Code must be 4–6 numeric digits (e.g. 9983 or 998313)."
            )
        return code

    def clean_gst_rate(self):
        rate = self.cleaned_data.get("gst_rate", "").strip()
        if rate and rate not in VALID_GST_RATE_VALUES:
            raise forms.ValidationError(
                "Select a valid GST rate from the approved list."
            )
        return rate

    def clean_uqc(self):
        uqc = self.cleaned_data.get("uqc", "").strip()
        if uqc and uqc not in VALID_UQC_VALUES:
            raise forms.ValidationError(
                "Select a valid Unit / UQC from the controlled list."
            )
        return uqc

    def clean_unit_price(self):
        price = self.cleaned_data.get("unit_price")
        if price is None:
            raise forms.ValidationError("Unit Price is required.")
        if price <= Decimal("0"):
            raise forms.ValidationError("Unit Price must be greater than zero.")
        return price

    # ------------------------------------------------------------------
    # Cross-field validation
    # ------------------------------------------------------------------

    def clean(self):
        cleaned = super().clean()
        product_type   = cleaned.get("product_type")
        taxability     = cleaned.get("taxability_type")
        gst_rate       = cleaned.get("gst_rate", "")
        cess_applicable = cleaned.get("cess_applicable", False)
        cess_type      = cleaned.get("cess_type", "")
        cess_amount    = cleaned.get("cess_rate_or_amount")
        uqc            = cleaned.get("uqc", "")
        price_basis    = cleaned.get("price_basis", "")

        # --- Classification ---
        if product_type == ProductType.GOODS:
            hsn = cleaned.get("hsn_code", "").strip()
            if not hsn:
                self.add_error("hsn_code", "HSN Code is required for Goods.")
            # Clear SAC when product is Goods
            cleaned["sac_code"] = ""

        elif product_type == ProductType.SERVICE:
            sac = cleaned.get("sac_code", "").strip()
            if not sac:
                self.add_error("sac_code", "SAC Code is required for Services.")
            # Clear HSN when product is Service
            cleaned["hsn_code"] = ""

        # --- GST Rate ---
        if taxability == TaxabilityType.TAXABLE:
            if not gst_rate:
                self.add_error("gst_rate", "GST Rate is required for Taxable products.")
            else:
                cleaned["gst_rate"] = Decimal(gst_rate)
        else:
            # For Exempt / Nil-rated / Non-GST, store 0 but do not require selection
            cleaned["gst_rate"] = Decimal("0.00")

        # --- Cess ---
        if cess_applicable:
            if not cess_type:
                self.add_error("cess_type", "Cess Type is required when Cess is applicable.")
            if cess_amount is None:
                self.add_error(
                    "cess_rate_or_amount",
                    "Cess Rate / Amount is required when Cess is applicable.",
                )
        else:
            # Clear cess fields when not applicable
            cleaned["cess_type"] = ""
            cleaned["cess_rate_or_amount"] = None

        # --- UQC ---
        if product_type == ProductType.GOODS and not uqc:
            self.add_error("uqc", "Unit / UQC is required for Goods.")

        # --- Price Basis ---
        if not price_basis:
            self.add_error("price_basis", "Price Basis (Inclusive / Exclusive) is required.")

        return cleaned
