"""
apps/products/models.py — Product Models

Product V1: a minimal, organization-scoped product/service master
for the Advance Billing invoice workflow.

Architecture principle:
    Product stores what the item *is*, how it is *priced*, and its
    default *tax characteristics*.  The Invoice Engine determines the
    actual CGST/SGST/UTGST or IGST split for each transaction using
    supplier location, place of supply, and transaction context.

See docs/PRODUCT_V1_POLICY.md for the full V1 scope and exclusions.
"""
import uuid
from decimal import Decimal

from django.db import models

from apps.common.models import TimeStampedModel
from apps.organization.models import Organization
from .gst_config import GST_RATE_CHOICES, UQC_CHOICES, GST_RATE_DEFAULT


# ---------------------------------------------------------------------------
# Choice enumerations
# ---------------------------------------------------------------------------

class ProductType(models.TextChoices):
    GOODS   = "goods",   "Goods"
    SERVICE = "service", "Service"


class TaxabilityType(models.TextChoices):
    TAXABLE   = "taxable",   "Taxable"
    EXEMPT    = "exempt",    "Exempt"
    NIL_RATED = "nil_rated", "Nil-rated"
    NON_GST   = "non_gst",  "Non-GST"


class PriceBasis(models.TextChoices):
    INCLUSIVE = "inclusive", "Inclusive of GST"
    EXCLUSIVE = "exclusive", "Exclusive of GST"


class CessType(models.TextChoices):
    PERCENTAGE   = "percentage",    "Percentage"
    FIXED_AMOUNT = "fixed_amount",  "Fixed Amount"


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------

class Product(TimeStampedModel):
    """
    Product / Service master record, scoped to an Organization.

    Contains tax characteristics and default pricing that are snapshotted
    into invoice lines at the time of invoice creation.  Editing the
    Product master never alters historical invoice data.

    V1 intentionally excludes: SKU, Discount, MRP, Export/SEZ/LUT,
    Batch/Expiry/Manufacturing, Inventory, Active/Inactive status,
    external GST/HSN APIs.
    """

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Stable public identifier used in URLs.",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="products",
        help_text="The organization that owns this product record.",
    )

    # ------------------------------------------------------------------
    # Product / Service Name
    # ------------------------------------------------------------------
    name = models.CharField(
        max_length=255,
        help_text=(
            "Product / Service Name as it should appear on invoices. "
            "Mandatory for both Goods and Services."
        ),
    )

    # ------------------------------------------------------------------
    # Product Type
    # ------------------------------------------------------------------
    product_type = models.CharField(
        max_length=10,
        choices=ProductType.choices,
        default=ProductType.GOODS,
        help_text="Goods → HSN required; Service → SAC required.",
    )

    # ------------------------------------------------------------------
    # Classification (HSN / SAC)
    # Stored as strings; never integers.
    # ------------------------------------------------------------------
    hsn_code = models.CharField(
        max_length=8,
        blank=True,
        help_text=(
            "Harmonised System of Nomenclature (HSN) code for Goods. "
            "2–8 numeric digits. Required when product_type is Goods."
        ),
    )
    sac_code = models.CharField(
        max_length=6,
        blank=True,
        help_text=(
            "Services Accounting Code (SAC) for Services. "
            "4–6 numeric digits. Required when product_type is Service."
        ),
    )

    # ------------------------------------------------------------------
    # Tax Profile
    # ------------------------------------------------------------------
    taxability_type = models.CharField(
        max_length=12,
        choices=TaxabilityType.choices,
        default=TaxabilityType.TAXABLE,
        help_text=(
            "Taxability classification: Taxable / Exempt / Nil-rated / Non-GST. "
            "Each classification has distinct legal meaning under GST."
        ),
    )
    gst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal(GST_RATE_DEFAULT),
        help_text=(
            "Applicable GST rate percentage for this product (e.g. 18.00 for 18%). "
            "Sourced from centralized GST rate configuration in gst_config.py. "
            "Relevant when taxability_type is Taxable; stored but not enforced "
            "for Exempt / Nil-rated / Non-GST items."
        ),
    )

    # Cess
    cess_applicable = models.BooleanField(
        default=False,
        help_text="Whether GST Cess applies to this product.",
    )
    cess_type = models.CharField(
        max_length=14,
        choices=CessType.choices,
        blank=True,
        help_text="Cess calculation method: Percentage or Fixed Amount per unit.",
    )
    cess_rate_or_amount = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text=(
            "When cess_type=Percentage: the cess percentage. "
            "When cess_type=Fixed Amount: the fixed amount per unit."
        ),
    )

    # Reverse Charge
    reverse_charge_applicable = models.BooleanField(
        default=False,
        help_text=(
            "Whether this product is subject to Reverse Charge Mechanism (RCM). "
            "This is a product-level default; the Invoice Engine makes the "
            "final RCM determination for each transaction."
        ),
    )

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------
    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text=(
            "Base unit price in INR. "
            "See price_basis to determine whether GST is included."
        ),
    )
    price_basis = models.CharField(
        max_length=10,
        choices=PriceBasis.choices,
        default=PriceBasis.EXCLUSIVE,
        help_text=(
            "Inclusive: unit_price already contains GST. "
            "Exclusive: GST is added on top of unit_price by the Invoice Engine."
        ),
    )
    uqc = models.CharField(
        max_length=3,
        help_text=(
            "Unique Quantity Code (CBIC). "
            "Required for Goods (Rule 46 — GST invoice rules). "
            "Controlled list from gst_config.UQC_CHOICES."
        ),
    )

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------
    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "name"]),
            models.Index(fields=["organization", "product_type"]),
        ]

    def __str__(self) -> str:
        code = self.hsn_code if self.product_type == ProductType.GOODS else self.sac_code
        return f"{self.name} [{self.get_product_type_display()}] {code or '—'}"

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------
    @property
    def is_goods(self) -> bool:
        return self.product_type == ProductType.GOODS

    @property
    def is_service(self) -> bool:
        return self.product_type == ProductType.SERVICE

    @property
    def classification_code(self) -> str:
        """Returns the applicable HSN or SAC code."""
        return self.hsn_code if self.is_goods else self.sac_code

    @property
    def is_taxable(self) -> bool:
        return self.taxability_type == TaxabilityType.TAXABLE

    # ------------------------------------------------------------------
    # Invoice snapshot
    # ------------------------------------------------------------------
    def as_invoice_snapshot(self) -> dict:
        """
        Return a point-in-time snapshot of this product's billing attributes.

        The Invoice Engine copies this dict into each invoice line when the
        product is selected.  Subsequent edits to the Product master do NOT
        alter already-created invoice lines, preserving historical correctness.

        The Invoice Engine is responsible for adding transaction-specific
        values (quantity, discount, CGST/SGST/IGST split, cess amounts,
        place of supply, etc.) after receiving this snapshot.
        """
        return {
            "product_id":              str(self.pk),
            "product_uuid":            str(self.uuid),
            "product_name":            self.name,
            "product_type":            self.product_type,
            "hsn_code":                self.hsn_code,
            "sac_code":                self.sac_code,
            "classification_code":     self.classification_code,
            "taxability_type":         self.taxability_type,
            "gst_rate":                str(self.gst_rate),
            "cess_applicable":         self.cess_applicable,
            "cess_type":               self.cess_type or None,
            "cess_rate_or_amount":     str(self.cess_rate_or_amount) if self.cess_rate_or_amount is not None else None,
            "reverse_charge_applicable": self.reverse_charge_applicable,
            "unit_price":              str(self.unit_price),
            "price_basis":             self.price_basis,
            "uqc":                     self.uqc,
        }
