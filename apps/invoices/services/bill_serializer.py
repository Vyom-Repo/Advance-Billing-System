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
import os
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
    inv_dict = invoice if isinstance(invoice, dict) else {}
    cust_dict = customer if isinstance(customer, dict) else {}
    items_list = [i for i in items if isinstance(i, dict)] if isinstance(items, (list, tuple)) else []
    comp_dict = company if isinstance(company, dict) else {}

    company_serialized = _serialize_company(comp_dict, org)
    bill_serialized = _serialize_invoice(inv_dict, company_serialized, org)

    tax_info = _compute_tax_breakdown(items_list, bill_serialized["tax_total"], inv_dict)
    bill_serialized.update(tax_info)

    return {
        "bill":        bill_serialized,
        "company":     company_serialized,
        "customer":    _serialize_customer(cust_dict),
        "items":       [_serialize_item(i, idx) for idx, i in enumerate(items_list, start=1)],
        "gst_summary": _build_gst_summary(items_list),
    }



# ---------------------------------------------------------------------------
# Private serializers
# ---------------------------------------------------------------------------

def _serialize_invoice(inv: dict, company: dict | None = None, org: Any = None) -> dict:
    """
    Canonical invoice-level dict.  All templates read from this shape.

    Fields prefixed with ``raw_`` are accepted from legacy data sources and
    normalised here so templates never need to know the original key name.
    """
    comp = company if isinstance(company, dict) else {}
    qr_code_url = inv.get("qr_code_url") or _file_url(getattr(org, "qr_code", None)) or comp.get("qr_code_url")
    terms = inv.get("terms") or comp.get("terms_and_conditions") or getattr(org, "terms_and_conditions", "")

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
        "round_off":       _to_float(inv.get("round_off", 0)),
        "grand_total":     _to_float(inv.get("total") or inv.get("grand_total", 0)),
        "amount_payable":  _to_float(inv.get("amount_payable") or inv.get("total", 0)),
        "amount_paid":     _to_float(inv.get("amount_paid", 0)),
        "amount_due":      _to_float(inv.get("amount_due", 0)),
        "amount_in_words": inv.get("amount_in_words", ""),

        # Narrative
        "notes":           inv.get("notes", ""),
        "terms":           terms,

        # Assets
        "qr_code_url":     qr_code_url,
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
    qr_code_url   = _file_url(getattr(org, "qr_code", None))   or company.get("qr_code_url")
    terms_and_conditions = getattr(org, "terms_and_conditions", "") or company.get("terms_and_conditions", "")
    signature_mode = company.get("signature_mode") or getattr(org, "signature_mode", "none")
    authorized_signatory_name = company.get("authorized_signatory_name") or getattr(org, "authorized_signatory_name", "")
    show_disclaimer = company.get("show_computer_generated_disclaimer") if "show_computer_generated_disclaimer" in company else getattr(org, "show_computer_generated_disclaimer", False)

    return {
        # Identity
        "name":                               company.get("name", ""),
        "legal_name":                         company.get("legal_name") or company.get("name", ""),
        "gstin":                              company.get("gstin", ""),
        "pan":                                company.get("pan", ""),
        "state_code":                         company.get("state_code", ""),
        "terms_and_conditions":               terms_and_conditions,
        "signature_mode":                     signature_mode,
        "authorized_signatory_name":          authorized_signatory_name,
        "show_computer_generated_disclaimer": show_disclaimer,

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
        "qr_code_url":   qr_code_url,

        # Bank details
        "bank_name":      company.get("bank_name", ""),
        "acc_no":         company.get("acc_no", ""),
        "ifsc":           company.get("ifsc", ""),
        "acc_name":       company.get("acc_name", ""),
        "branch":         company.get("branch", ""),
        "upi_id":         company.get("upi_id", ""),
    }


import re


def _normalize_address_field(text: str) -> str:
    if not text:
        return ""
    clean = text.strip().lower()
    clean = re.sub(r"[\s,\.\-_]+", " ", clean).strip()
    return clean


def _state_name_from_code(code: str) -> str:
    if not code:
        return ""
    try:
        from apps.organization.services import LocalGSTValidator
        return LocalGSTValidator.STATE_CODES.get(str(code).zfill(2), "")
    except Exception:
        pass
    return ""


def _state_code_from_name(state_name: str) -> str:
    if not state_name:
        return ""
    state_clean = state_name.strip().lower()
    try:
        from apps.organization.services import LocalGSTValidator
        for code, name in LocalGSTValidator.STATE_CODES.items():
            if name.lower() == state_clean or name.lower().startswith(state_clean):
                return code
    except Exception:
        pass
    return ""


def _serialize_customer(customer: dict) -> dict:
    """Canonical buyer/customer dict."""
    cust = customer if isinstance(customer, dict) else {}
    gstin = (cust.get("gstin") or "").strip()

    # Billing address
    b_addr = (cust.get("address") or cust.get("billing_address_line_1") or "").strip()
    b_city = (cust.get("city") or cust.get("billing_city") or "").strip()
    b_state = (cust.get("state") or cust.get("billing_state") or "").strip()
    b_pin = (cust.get("pincode") or cust.get("billing_pin_code") or "").strip()
    b_state_code = (cust.get("state_code") or cust.get("billing_state_code") or "").strip()

    if not b_state_code and gstin and len(gstin) >= 2 and gstin[:2].isdigit():
        b_state_code = gstin[:2]
    if not b_state_code and b_state:
        b_state_code = _state_code_from_name(b_state)
    if not b_state and b_state_code:
        b_state = _state_name_from_code(b_state_code)

    shipping_same = cust.get("shipping_same_as_billing")

    # Shipping address
    s_addr = (cust.get("shipping_address") or cust.get("shipping_address_line_1") or "").strip()
    s_city = (cust.get("shipping_city") or "").strip()
    s_state = (cust.get("shipping_state") or "").strip()
    s_pin = (cust.get("shipping_pincode") or cust.get("shipping_pin_code") or "").strip()
    s_state_code = (cust.get("shipping_state_code") or "").strip()

    # Sanitization 1: If s_addr is a 2-digit numeric state code, move it to s_state_code
    if s_addr and s_addr.isdigit() and len(s_addr) <= 2:
        if not s_state_code:
            s_state_code = s_addr.zfill(2)
        s_addr = ""

    # Sanitization 2: If s_state is a 2-digit numeric state code, move it to s_state_code & resolve state name
    if s_state and s_state.isdigit() and len(s_state) <= 2:
        if not s_state_code:
            s_state_code = s_state.zfill(2)
        s_state = _state_name_from_code(s_state_code)

    if not s_state_code and s_state:
        s_state_code = _state_code_from_name(s_state)
    if not s_state and s_state_code:
        s_state = _state_name_from_code(s_state_code)

    if shipping_same is True:
        is_different = False
    else:
        has_shipping = bool(s_addr or s_city or (s_state and s_state != b_state) or (s_pin and s_pin != b_pin))

        # Normalized comparison to compare actual address content
        norm_b_addr = _normalize_address_field(b_addr)
        norm_s_addr = _normalize_address_field(s_addr)
        norm_b_city = _normalize_address_field(b_city)
        norm_s_city = _normalize_address_field(s_city)
        norm_b_state = _normalize_address_field(b_state)
        norm_s_state = _normalize_address_field(s_state)
        norm_b_pin = _normalize_address_field(b_pin)
        norm_s_pin = _normalize_address_field(s_pin)

        is_different = has_shipping and (
            (norm_s_addr and norm_s_addr != norm_b_addr) or
            (norm_s_city and norm_s_city != norm_b_city) or
            (norm_s_state and norm_s_state != norm_b_state) or
            (norm_s_pin and norm_s_pin != norm_b_pin)
        )

    shipping_parts = [p for p in [s_addr, s_city, f"{s_state} - {s_pin}" if s_state and s_pin else (s_state or s_pin)] if p]
    shipping_full_address = ", ".join(shipping_parts) if is_different else ""

    if is_different:
        res_state = s_state
        res_state_code = s_state_code
    else:
        res_state = b_state
        res_state_code = b_state_code

    if res_state and res_state_code:
        res_state_display = f"{res_state} - {res_state_code}"
    elif res_state:
        res_state_display = res_state
    elif res_state_code:
        res_state_display = res_state_code
    else:
        res_state_display = ""

    return {
        "name":                        cust.get("name", ""),
        "gstin":                       gstin,
        "phone":                       cust.get("phone", ""),
        "email":                       cust.get("email", ""),

        # Billing address
        "address":                     b_addr,
        "city":                        b_city,
        "state":                       b_state,
        "pincode":                     b_pin,
        "state_code":                  b_state_code,

        # Shipping address (may be same as billing)
        "shipping_name":               cust.get("shipping_name", ""),
        "shipping_address":            s_addr,
        "shipping_city":               s_city,
        "shipping_state":              s_state,
        "shipping_pincode":            s_pin,
        "shipping_state_code":         s_state_code,
        "has_different_shipping_address": is_different,
        "shipping_full_address":       shipping_full_address,

        # Resolved state metadata
        "resolved_state":              res_state,
        "resolved_state_code":         res_state_code,
        "resolved_state_display":      res_state_display,
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
        "pretax_amount":  _to_float(item.get("taxable_value") or (rate * quantity if rate else amount)),

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
    """
    Convert a Django ImageField/FileField to a valid URL for WeasyPrint.
    Returns HTTP(S) URL for remote storage (Cloudinary) or file:// URL for local disk storage.
    """
    if not field:
        return None

    # 1. Check for remote storage URL (Cloudinary / S3 / HTTP / HTTPS)
    try:
        url = getattr(field, "url", None)
        if url and (url.startswith("http://") or url.startswith("https://")):
            return url
    except Exception:
        pass

    # 2. Check for local filesystem path (FileSystemStorage)
    try:
        path = getattr(field, "path", None)
        if path and os.path.exists(path):
            return f"file://{path}"
    except Exception:
        pass

    return None


def _currency_symbol(code: str) -> str:
    return {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}.get(code, code)


def _compute_tax_breakdown(items_list: list[dict], tax_total: float, inv_dict: dict) -> dict:
    """
    Computes CGST and SGST totals and rates from invoice data or line items.
    Guarantees cgst_total + sgst_total == tax_total.
    """
    raw_cgst = _to_float(inv_dict.get("cgst_total"))
    raw_sgst = _to_float(inv_dict.get("sgst_total"))

    if (raw_cgst > 0 or raw_sgst > 0) and abs((raw_cgst + raw_sgst) - tax_total) < 0.02:
        cgst_total = round(raw_cgst, 2)
        sgst_total = round(raw_sgst, 2)
    else:
        half = round(tax_total / 2.0, 2)
        cgst_total = half
        sgst_total = round(tax_total - half, 2)

    distinct_rates = []
    if items_list:
        for it in items_list:
            tp = _to_float(it.get("tax_pct", 0))
            if tp > 0 and tp not in distinct_rates:
                distinct_rates.append(tp)

    if len(distinct_rates) == 1:
        single_rate = distinct_rates[0]
        cgst_rate = round(single_rate / 2.0, 2)
        sgst_rate = round(single_rate / 2.0, 2)
        breakdown = [{
            "tax_pct": single_rate,
            "cgst_rate": cgst_rate,
            "sgst_rate": sgst_rate,
            "cgst_amount": cgst_total,
            "sgst_amount": sgst_total,
        }]
    elif len(distinct_rates) > 1:
        by_rate = {}
        for it in items_list:
            tp = _to_float(it.get("tax_pct", 0))
            amt = _to_float(it.get("amount", 0))
            base = amt / (1 + tp / 100.0) if tp else amt
            tax_amt = amt - base
            by_rate[tp] = by_rate.get(tp, 0.0) + tax_amt

        breakdown = []
        accum_cgst = 0.0
        accum_sgst = 0.0
        sorted_rates = sorted(by_rate.keys())
        for idx, tp in enumerate(sorted_rates):
            t_amt = by_rate[tp]
            if idx == len(sorted_rates) - 1:
                c_amt = round(cgst_total - accum_cgst, 2)
                s_amt = round(sgst_total - accum_sgst, 2)
            else:
                c_amt = round(t_amt / 2.0, 2)
                s_amt = round(t_amt - c_amt, 2)
                accum_cgst += c_amt
                accum_sgst += s_amt
            half_r = round(tp / 2.0, 2)
            breakdown.append({
                "tax_pct": tp,
                "cgst_rate": half_r,
                "sgst_rate": half_r,
                "cgst_amount": c_amt,
                "sgst_amount": s_amt,
            })
        cgst_rate = round(sorted_rates[0] / 2.0, 2)
        sgst_rate = round(sorted_rates[0] / 2.0, 2)
    else:
        tax_pct_hint = _to_float(inv_dict.get("tax_pct", 0))
        cgst_rate = round(tax_pct_hint / 2.0, 2)
        sgst_rate = round(tax_pct_hint / 2.0, 2)
        breakdown = [{
            "tax_pct": tax_pct_hint,
            "cgst_rate": cgst_rate,
            "sgst_rate": sgst_rate,
            "cgst_amount": cgst_total,
            "sgst_amount": sgst_total,
        }]

    return {
        "cgst_total": cgst_total,
        "sgst_total": sgst_total,
        "cgst_rate": cgst_rate,
        "sgst_rate": sgst_rate,
        "tax_breakdown": breakdown,
    }

