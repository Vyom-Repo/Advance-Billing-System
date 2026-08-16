"""
apps/products/gst_config.py — Centralized GST Rate and UQC Configuration

All controlled lists for the Product module live here.
Add or update rates/units in this single file — never scatter
numeric literals or unit codes across templates and Python code.

References:
  - CBIC GST rate notifications
  - IRIS IRP Tax Rate Master (40% rate added September 2025)
  - CBIC UQC list under GST (Unique Quantity Codes)
"""
from decimal import Decimal

# ---------------------------------------------------------------------------
# GST Rates
# Each entry: (Decimal-string value, human-readable label)
# The Decimal string is stored in the database; the label is shown in the UI.
# ---------------------------------------------------------------------------
GST_RATE_CHOICES = [
    ("0.00",  "0%"),
    ("0.25",  "0.25%"),
    ("1.50",  "1.5%"),
    ("3.00",  "3%"),
    ("5.00",  "5%"),
    ("7.50",  "7.5%"),
    ("12.00", "12%"),
    ("18.00", "18%"),
    ("28.00", "28%"),
    ("40.00", "40%"),  # Added to IRIS IRP Tax Rate Master, September 2025
]

# Set of valid rate values for form validation
VALID_GST_RATE_VALUES = frozenset(v for v, _ in GST_RATE_CHOICES)

# Default rate for new products
GST_RATE_DEFAULT = "18.00"


# ---------------------------------------------------------------------------
# UQC — Unique Quantity Codes
# Based on CBIC official Unique Quantity Codes list under GST.
# This list is intentionally maintainable; add new codes here as needed.
# For Goods, a valid UQC is required (Rule 46 — GST invoice rules).
# For Services, UQC is captured but the strict Goods-specific rule does not apply.
# ---------------------------------------------------------------------------
UQC_CHOICES = [
    ("",    "Select Unit"),
    ("BAG", "BAG – Bags"),
    ("BDL", "BDL – Bundles"),
    ("BOX", "BOX – Boxes"),
    ("BTL", "BTL – Bottles"),
    ("CBM", "CBM – Cubic Metres"),
    ("CMS", "CMS – Centimetres"),
    ("DOZ", "DOZ – Dozens"),
    ("DRM", "DRM – Drums"),
    ("GMS", "GMS – Grammes"),
    ("GRS", "GRS – Gross"),
    ("KGS", "KGS – Kilograms"),
    ("KLR", "KLR – Kilolitres"),
    ("KME", "KME – Kilometres"),
    ("LTR", "LTR – Litres"),
    ("MLS", "MLS – Millilitres"),
    ("MLT", "MLT – Metric Tonnes"),
    ("MTR", "MTR – Metres"),
    ("NOS", "NOS – Numbers"),
    ("OTH", "OTH – Others"),
    ("PAC", "PAC – Packs"),
    ("PCS", "PCS – Pieces"),
    ("ROL", "ROL – Rolls"),
    ("SET", "SET – Sets"),
    ("SQF", "SQF – Square Feet"),
    ("SQM", "SQM – Square Metres"),
    ("SQY", "SQY – Square Yards"),
    ("TUB", "TUB – Tubes"),
    ("UNT", "UNT – Units"),
]

# Set of valid UQC values (excluding empty sentinel) for validation
VALID_UQC_VALUES = frozenset(v for v, _ in UQC_CHOICES if v)
