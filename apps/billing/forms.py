"""apps/billing/forms.py — Invoice Forms"""
from django import forms
from django.forms import inlineformset_factory

from apps.billing.models import Invoice, InvoiceLine, DiscountType
from apps.customers.models import Customer
from apps.products.models import Product
from apps.organization.services import LocalGSTValidator


# ---------------------------------------------------------------------------
# Canonical state code choices — used for shipping_state and place_of_supply
# ---------------------------------------------------------------------------

STATE_CODE_CHOICES = [("", "Select State")] + sorted(
    [(code, f"{name} ({code})") for code, name in LocalGSTValidator.STATE_CODES.items()],
    key=lambda x: x[1]
)


# ---------------------------------------------------------------------------
# InvoiceCustomerForm (preserved from Phase 04)
# ---------------------------------------------------------------------------

class InvoiceCustomerForm(forms.ModelForm):
    """
    Minimal form to integrate the existing Customer master with Invoice.
    Enforces organization-scoped lookup and protects against cross-tenant assignment.
    """
    class Meta:
        model = Invoice
        fields = ['customer']

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop('organization', None)
        if not self.organization:
            raise ValueError("InvoiceCustomerForm requires an 'organization' kwarg.")
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(organization=self.organization)
        self.fields['customer'].required = False


# ---------------------------------------------------------------------------
# InvoiceForm — full invoice header form for Create / Edit Draft
# ---------------------------------------------------------------------------

class InvoiceForm(forms.ModelForm):
    """
    Form for creating and updating Invoice header fields.
    Handles dates, customer selection, shipping address, notes, terms.
    Does NOT handle line items (managed by InvoiceLineFormSet).
    Does NOT perform financial calculation — the backend is authoritative.
    Does NOT expose place_of_supply as a user field — it is derived from the
    shipping state (or billing state when 'same as billing' is checked) in
    resolve_place_of_supply() and set by the view before saving the invoice.
    Draft save must NOT call finalize_invoice().
    """

    # Shipping state as a canonical state-code dropdown.
    # Submits a 2-digit state code to avoid all fuzzy-matching risk.
    shipping_state = forms.ChoiceField(
        choices=STATE_CODE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-control", "id": "id_shipping_state"}),
    )

    class Meta:
        model = Invoice
        fields = [
            "customer", "invoice_date", "due_date",
            "shipping_same_as_billing", "shipping_address_line_1",
            "shipping_city", "shipping_state", "shipping_pincode",
            "notes", "terms",
        ]
        widgets = {
            "customer": forms.Select(attrs={"class": "form-control", "id": "id_customer"}),
            "invoice_date": forms.DateInput(attrs={"class": "form-control", "type": "date", "id": "id_invoice_date"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date", "id": "id_due_date"}),
            "shipping_same_as_billing": forms.CheckboxInput(attrs={"id": "id_shipping_same_as_billing", "class": "checkbox-input"}),
            "shipping_address_line_1": forms.TextInput(attrs={"class": "form-control", "placeholder": "Street address, building, suite", "id": "id_shipping_address_line_1"}),
            "shipping_city": forms.TextInput(attrs={"class": "form-control", "placeholder": "City or town", "id": "id_shipping_city"}),
            "shipping_pincode": forms.TextInput(attrs={"class": "form-control", "placeholder": "PIN code", "maxlength": "10", "id": "id_shipping_pincode"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Optional notes to the customer", "id": "id_notes"}),
            "terms": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Payment terms, delivery terms, etc.", "id": "id_terms"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

        if self.organization:
            self.fields["customer"].queryset = Customer.objects.filter(
                organization=self.organization
            ).order_by("name")
        else:
            self.fields["customer"].queryset = Customer.objects.none()

        self.fields["customer"].required = False
        self.fields["due_date"].required = False
        self.fields["notes"].required = False
        self.fields["terms"].required = False

        # Pre-populate notes from InvoicePreference on new invoices
        if not self.instance.pk and self.organization:
            try:
                pref = self.organization.owner.invoice_preference
                if not self.initial.get("notes"):
                    self.fields["notes"].initial = pref.default_notes
            except Exception:
                pass

    def clean_customer(self):
        customer = self.cleaned_data.get("customer")
        if customer and self.organization:
            if customer.organization_id != self.organization.id:
                raise forms.ValidationError("Selected customer does not belong to your organization.")
        return customer

    def clean(self):
        cleaned = super().clean()
        invoice_date = cleaned.get("invoice_date")
        due_date = cleaned.get("due_date")
        if invoice_date and due_date and due_date < invoice_date:
            self.add_error("due_date", "Due Date cannot be before Invoice Date.")
        return cleaned


# ---------------------------------------------------------------------------
# InvoiceLineForm — per-line item form for the inline formset
# ---------------------------------------------------------------------------

class InvoiceLineForm(forms.ModelForm):
    """
    Form for a single InvoiceLine within an Invoice.
    Enforces organization-scoped product lookup.
    Handles product, description, quantity, unit_price, discount_type, discount_value.
    """

    class Meta:
        model = InvoiceLine
        fields = ["product", "description", "quantity", "unit_price", "discount_type", "discount_value"]
        widgets = {
            "description": forms.Textarea(attrs={
                "class": "form-control line-description",
                "rows": "2",
                "placeholder": "Description (optional)",
            })
        }

    def __init__(self, *args, **kwargs):
        self.organization = kwargs.pop("organization", None)
        if not self.organization:
            raise ValueError("InvoiceLineForm requires an 'organization' kwarg.")
        super().__init__(*args, **kwargs)

        self.fields["product"].queryset = Product.objects.filter(
            organization=self.organization
        ).order_by("name")
        self.fields["product"].widget.attrs.update({"class": "form-control line-product-select"})
        self.fields["description"].required = False
        self.fields["quantity"].widget.attrs.update({"class": "form-control line-qty", "step": "0.001", "min": "0.001"})
        self.fields["unit_price"].widget.attrs.update({"class": "form-control line-rate", "step": "0.01", "min": "0"})
        self.fields["discount_type"].widget.attrs.update({"class": "form-control line-discount-type"})
        self.fields["discount_value"].widget.attrs.update({"class": "form-control line-discount-value", "step": "0.01", "min": "0"})

        # Use Product price and description as initial defaults
        if "initial" in kwargs and kwargs["initial"].get("product"):
            product_id = kwargs["initial"]["product"]
            try:
                product = Product.objects.get(id=product_id, organization=self.organization)
                if "unit_price" not in kwargs.get("initial", {}):
                    self.fields["unit_price"].initial = product.unit_price
                if "description" not in kwargs.get("initial", {}):
                    self.fields["description"].initial = product.description
            except Product.DoesNotExist:
                pass

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get("product")
        qty = cleaned_data.get("quantity")

        if product and self.organization:
            if product.organization_id != self.organization.id:
                self.add_error("product", "Selected product does not belong to your organization.")

        if qty is not None and qty <= 0:
            self.add_error("quantity", "Quantity must be greater than zero.")

        unit_price = cleaned_data.get("unit_price")
        if product and unit_price is None:
            cleaned_data["unit_price"] = product.unit_price

        discount_type = cleaned_data.get("discount_type")
        if discount_type == "none":
            cleaned_data["discount_value"] = 0

        desc = cleaned_data.get("description")
        if desc:
            cleaned_data["description"] = desc.strip()
        else:
            cleaned_data["description"] = ""

        return cleaned_data


# ---------------------------------------------------------------------------
# InvoiceLineFormSet — Django inline formset for line items
# ---------------------------------------------------------------------------

def make_invoice_line_formset(organization, extra=1):
    """
    Factory that creates an InvoiceLine inline formset with organization scoping.
    JavaScript may dynamically add/remove formset rows;
    Django remains responsible for validation and persistence.
    """
    BaseFormSet = inlineformset_factory(
        Invoice,
        InvoiceLine,
        form=InvoiceLineForm,
        fields=["product", "description", "quantity", "unit_price", "discount_type", "discount_value"],
        extra=extra,
        can_delete=True,
        min_num=0,
        validate_min=False,
    )

    class OrganizationScopedLineFormSet(BaseFormSet):
        def get_form_kwargs(self, index):
            kwargs = super().get_form_kwargs(index)
            kwargs["organization"] = organization
            return kwargs

    return OrganizationScopedLineFormSet
