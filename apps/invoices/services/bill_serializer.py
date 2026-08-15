"""
apps/invoices/services/bill_serializer.py

Canonical bill data serializer.

Every one of the 8 PDF templates receives bill data in exactly the shape
produced here — no template-specific data-shaping is allowed downstream.

Shape contract
--------------
The rendered template context is:

    {
        "bill":        <dict>   — invoice-level metadata & totals
        "company":     <dict>   — seller / organization info + bank details
        "customer":    <dict>   — buyer / customer info
        "items":       [<dict>] — line items (all optional fields present, None if N/A)
        "gst_summary": [<dict>] — per-HSN GST breakdown rows (for templates that show it)
        "config":      <dict>   — resolved render config (see resolve_render_config)
        "layout_frame":<dict>   — WeasyPrint page geometry
        "org":         <obj>    — Organization ORM instance (for file:// image paths)
    }

``serialize_bill_for_render`` produces the first five keys.
``config`` and ``layout_frame`` are added by the rendering pipeline.
"""

from __future__ import annotations
from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def serialize_bill_for_render(
    invoice: dict | None,
    customer: dict | None,
    items: list[dict] | None,
    company: dict | None,
    org: Any = None,
) -> dict:
    """
    Merge raw data dicts into the canonical render context.

    Parameters
    ----------
    invoice  : dict  — fields from Invoice model or SampleDataService.sample_invoice()
    customer : dict  — fields from Customer model or SampleDataService.sample_customer()
    items    : list  — list of item dicts from SampleDataService.sample_items() or real items
    company  : dict  — assembled by OrganizationService or SampleDataService.sample_company()
    org      : Organization ORM instance or None

    Returns
    -------
    dict with keys: bill, company, customer, items, gst_summary
    """
    inv_dict = invoice if isinstance(invoice, dict) else {}
    cust_dict = customer if isinstance(customer, dict) else {}
    items_list = [i for i in items if isinstance(i, dict)] if isinstance(items, (list, tuple)) else []
    comp_dict = company if isinstance(company, dict) else {}

    return {
        "bill":        _serialize_invoice(inv_dict),
        "company":     _serialize_company(comp_dict, org),
        "customer":    _serialize_customer(cust_dict),
        "items":       [_serialize_item(i, idx) for idx, i in enumerate(items_list, start=1)],
        "gst_summary": _build_gst_summary(items_list),
    }


# ---------------------------------------------------------------------------
# Private serializers
# ---------------------------------------------------------------------------

def _serialize_invoice(inv: dict) -> dict:
    """
    Canonical invoice-level dict.  All templates read from this shape.

    Fields prefixed with ``raw_`` are accepted from legacy data sources and
    normalised here so templates never need to know the original key name.
    """
    return {
        # Identification
        "number":          inv.get("number") or inv.get("invoice_number") or "",
        "date":            inv.get("date") or inv.get("invoice_date") or "",
        "due_date":        inv.get("due_date") or "",
        "place_of_supply": inv.get("place_of_supply") or "",

        # Currency & formatting
        "currency":        inv.get("currency", "INR"),
        "currency_symbol": _currency_symbol(inv.get("currency", "INR")),

        # Totals
        "subtotal":        _to_float(inv.get("subtotal", 0)),
        "tax_total":       _to_float(inv.get("tax_total", 0)),
        "discount_total":  _to_float(inv.get("discount_total", 0)),
        "grand_total":     _to_float(inv.get("total") or inv.get("grand_total", 0)),
        "amount_payable":  _to_float(inv.get("amount_payable") or inv.get("total", 0)),
        "amount_paid":     _to_float(inv.get("amount_paid", 0)),
        "amount_due":      _to_float(inv.get("amount_due", 0)),
        "amount_in_words": inv.get("amount_in_words", ""),

        # Narrative
        "notes":           inv.get("notes", ""),
        "terms":           inv.get("terms", ""),

        # Assets
        "qr_code_url":     inv.get("qr_code_url"),

        # Payment info
        "payment_method":  inv.get("payment_method", ""),
        "payment_date":    inv.get("payment_date", ""),
    }


def _serialize_company(company: dict, org=None) -> dict:
    """
    Canonical company/seller dict.

    ``org`` is the ORM Organization instance; we derive file:// image paths
    from it when available so templates can use <img src="{{ company.logo_url }}">.
    """
    # Prefer live org data for image paths, fall back to pre-built URLs in company dict
    logo_url      = _file_url(getattr(org, "logo", None))      or company.get("logo_url")
    signature_url = _file_url(getattr(org, "signature", None))  or company.get("signature_url")
    letterhead_url= _file_url(getattr(org, "letterhead", None)) or company.get("letterhead_url")

    return {
        # Identity
        "name":           company.get("name", ""),
        "legal_name":     company.get("legal_name") or company.get("name", ""),
        "gstin":          company.get("gstin", ""),
        "pan":            company.get("pan", ""),
        "state_code":     company.get("state_code", ""),

        # Address
        "address":        company.get("address", ""),
        "city":           company.get("city", ""),
        "state":          company.get("state", ""),
        "pincode":        company.get("pincode", ""),
        "country":        company.get("country", "India"),

        # Contact
        "email":          company.get("email", ""),
        "phone":          company.get("phone", ""),
        "website":        company.get("website", ""),

        # Branding assets (file:// URLs for WeasyPrint)
        "logo_url":       logo_url,
        "signature_url":  signature_url,
        "letterhead_url": letterhead_url,

        # Bank details
        "bank_name":      company.get("bank_name", ""),
        "acc_no":         company.get("acc_no", ""),
        "ifsc":           company.get("ifsc", ""),
        "acc_name":       company.get("acc_name", ""),
        "branch":         company.get("branch", ""),
        "upi_id":         company.get("upi_id", ""),
    }


def _serialize_customer(customer: dict) -> dict:
    """Canonical buyer/customer dict."""
    return {
        "name":           customer.get("name", ""),
        "gstin":          customer.get("gstin", ""),
        "phone":          customer.get("phone", ""),
        "email":          customer.get("email", ""),

        # Billing address
        "address":        customer.get("address", ""),
        "city":           customer.get("city", ""),
        "state":          customer.get("state", ""),
        "pincode":        customer.get("pincode", ""),
        "state_code":     customer.get("state_code", ""),

        # Shipping address (may be same as billing)
        "shipping_name":    customer.get("shipping_name", ""),
        "shipping_address": customer.get("shipping_address", ""),
        "shipping_city":    customer.get("shipping_city", ""),
        "shipping_state":   customer.get("shipping_state", ""),
        "shipping_pincode": customer.get("shipping_pincode", ""),
    }


def _serialize_item(item: dict, index: int) -> dict:
    """
    Canonical line-item dict.  All optional fields are always present
    (set to None / 0 when not applicable) so templates can safely access
    ``{{ item.mrp }}`` without guard conditions causing template errors.
    """
    rate          = _to_float(item.get("rate", 0))
    quantity      = _to_float(item.get("quantity", 1))
    tax_pct       = _to_float(item.get("tax_pct", 0))
    amount        = _to_float(item.get("amount") or rate * quantity)
    taxable_value = _to_float(item.get("taxable_value") or amount / (1 + tax_pct / 100) if tax_pct else amount)
    tax_amount    = _to_float(item.get("tax_amount") or amount - taxable_value)

    return {
        # Identification
        "index":          index,
        "name":           item.get("name", ""),
        "description":    item.get("description", ""),
        "hsn":            item.get("hsn") or item.get("sac", ""),

        # Quantity & pricing
        "quantity":       quantity,
        "unit":           item.get("unit", ""),
        "rate":           rate,

        # MRP/discount columns (compact/mrp_discount templates)
        "mrp":            _to_float_or_none(item.get("mrp")),
        "discount":       _to_float_or_none(item.get("discount")),
        "discount_pct":   _to_float_or_none(item.get("discount_pct")),
        "selling_price":  _to_float_or_none(item.get("selling_price")),

        # Tax
        "tax_pct":        tax_pct,
        "taxable_value":  taxable_value,
        "tax_amount":     tax_amount,

        # Final amount
        "amount":         amount,

        # Sub-items / images (genz / modern templates)
        "sub_items":      item.get("sub_items", []),
        "image_urls":     item.get("image_urls", []),
    }


def _build_gst_summary(items: list[dict]) -> list[dict]:
    """
    Build per-HSN GST breakdown rows consumed by landscape_template and
    compact_template's tax summary table.

    Groups items by (hsn, tax_pct) and aggregates amounts.
    Uses CGST/SGST split (intra-state) — templates may suppress via config.
    """
    from collections import defaultdict

    buckets: dict[tuple, dict] = defaultdict(lambda: {
        "taxable": 0.0,
        "cgst_amount": 0.0,
        "sgst_amount": 0.0,
        "igst_amount": 0.0,
        "total_tax": 0.0,
    })

    for item in items:
        hsn     = item.get("hsn") or item.get("sac", "—")
        tax_pct = _to_float(item.get("tax_pct", 0))
        amount  = _to_float(item.get("amount") or 0)
        rate    = _to_float(item.get("rate", 0))
        qty     = _to_float(item.get("quantity", 1))
        base    = amount / (1 + tax_pct / 100) if tax_pct else amount
        tax_amt = amount - base

        key = (hsn, tax_pct)
        b = buckets[key]
        b["taxable"]     += base
        # Simple heuristic: split equally as CGST/SGST (intra-state).
        # Real invoices should supply explicit cgst/sgst; extend item schema when ready.
        b["cgst_amount"] += tax_amt / 2
        b["sgst_amount"] += tax_amt / 2
        b["total_tax"]   += tax_amt

    rows = []
    for (hsn, tax_pct), b in buckets.items():
        half_rate = round(tax_pct / 2, 1)
        rows.append({
            "hsn":          hsn,
            "tax_pct":      tax_pct,
            "taxable":      round(b["taxable"], 2),
            "cgst_rate":    half_rate,
            "cgst_amount":  round(b["cgst_amount"], 2),
            "sgst_rate":    half_rate,
            "sgst_amount":  round(b["sgst_amount"], 2),
            "igst_rate":    0,
            "igst_amount":  0.0,
            "total_tax":    round(b["total_tax"], 2),
            "is_total":     False,
        })

    # Total row
    if rows:
        rows.append({
            "hsn":          "TOTAL",
            "tax_pct":      None,
            "taxable":      round(sum(r["taxable"] for r in rows if not r.get("is_total")), 2),
            "cgst_rate":    None,
            "cgst_amount":  round(sum(r["cgst_amount"] for r in rows if not r.get("is_total")), 2),
            "sgst_rate":    None,
            "sgst_amount":  round(sum(r["sgst_amount"] for r in rows if not r.get("is_total")), 2),
            "igst_rate":    None,
            "igst_amount":  0.0,
            "total_tax":    round(sum(r["total_tax"] for r in rows if not r.get("is_total")), 2),
            "is_total":     True,
        })

    return rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _to_float_or_none(value) -> "float | None":
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _file_url(field) -> "str | None":
    """Convert a Django ImageField/FileField to a file:// URL for WeasyPrint."""
    if not field:
        return None
    try:
        return f"file://{field.path}"
    except Exception:
        return None


def _currency_symbol(code: str) -> str:
    return {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(code, code)
