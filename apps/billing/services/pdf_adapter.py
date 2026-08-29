"""
apps/billing/services/pdf_adapter.py

Adapts Phase 08 Invoice ORM instances into the simple dictionaries required
by the existing Phase 01 PDF serialization pipeline (bill_serializer.py).

This adapter is entirely side-effect free and performs no calculations.
"""

from apps.billing.models import Invoice

def _format_date(val):
    if not val:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, str) and len(val) == 10 and val[4] == "-" and val[7] == "-":
        parts = val.split("-")
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return str(val)


def invoice_to_pdf_dicts(invoice: Invoice):
    """
    Transforms the given Invoice ORM object into the four dictionary structures
    expected by serialize_bill_for_render():
    (invoice_dict, customer_dict, items_list, company_dict)
    
    This function reads historical snapshots directly from the Invoice/InvoiceLine,
    ensuring that post-issuance modifications to Customer/Product do not alter
    the generated PDF. No taxes or totals are recalculated.
    """
    # 1. Invoice Dict
    invoice_dict = {
        "number": invoice.invoice_number,
        "date": _format_date(invoice.invoice_date),
        "due_date": _format_date(invoice.due_date),
        "place_of_supply": invoice.place_of_supply,
        "destination": getattr(invoice, "destination", ""),
        "currency": invoice.currency,
        "subtotal": float(invoice.subtotal),
        "tax_total": float(invoice.cgst_total + invoice.sgst_total + invoice.igst_total + invoice.cess_total),
        "discount_total": float(invoice.discount_total),
        "grand_total": float(invoice.grand_total),
        "amount_payable": float(invoice.grand_total),
        "notes": invoice.notes,
        "terms": invoice.terms,
    }

    # 2. Customer Dict
    cust_obj = getattr(invoice, "customer", None)
    if cust_obj:
        street = cust_obj.billing_address_line_1
        if cust_obj.billing_address_line_2:
            street = f"{street}, {cust_obj.billing_address_line_2}"
        b_city = cust_obj.billing_city
        b_state = cust_obj.billing_state
        b_pin = cust_obj.billing_pin_code
        b_country = cust_obj.billing_country
    else:
        street = invoice.customer_billing_address_snapshot
        b_city = ""
        b_state = ""
        b_pin = ""
        b_country = ""

    customer_dict = {
        "name": invoice.customer_name_snapshot,
        "gstin": invoice.customer_gstin_snapshot,
        "address": street,
        "city": b_city,
        "state": b_state,
        "pincode": b_pin,
        "country": b_country,
        "state_code": invoice.customer_state_code_snapshot,

        "shipping_name": invoice.customer_name_snapshot,
        "shipping_address": getattr(invoice, "shipping_address_line_1", "") or getattr(invoice, "shipping_address", ""),
        "shipping_city": getattr(invoice, "shipping_city", ""),
        "shipping_state": getattr(invoice, "shipping_state", ""),
        "shipping_pincode": getattr(invoice, "shipping_pincode", ""),
        "shipping_state_code": getattr(invoice, "shipping_state_code", ""),
    }

    # 3. Items List
    items_list = []
    for line in invoice.lines.all().order_by('position'):
        items_list.append({
            "name": line.product_name_snapshot,
            "description": getattr(line, "description", "") or "",
            "hsn": line.hsn_sac_snapshot,
            "quantity": float(line.quantity),
            "unit": line.uqc_snapshot,
            "rate": float(line.unit_price),
            "discount": float(line.discount_amount),
            "taxable_value": float(line.taxable_value),
            "tax_pct": float(line.gst_rate_snapshot),
            "tax_amount": float(line.cgst_amount + line.sgst_amount + line.igst_amount + line.cess_amount),
            "amount": float(line.line_total),
        })

    # 4. Company Dict
    org = invoice.organization
    company_dict = {
        "name": org.business_name,
        "legal_name": org.legal_business_name,
        "gstin": org.gstin,
        "pan": org.pan,
        "state_code": org.state_code,
        "address": org.address_line_1,
        "city": org.city,
        "state": org.state,
        "pincode": org.pincode,
        "country": org.country,
        "email": org.business_email,
        "phone": org.phone_number,
        "terms_and_conditions": getattr(org, "terms_and_conditions", ""),
        "signature_mode": getattr(org, "signature_mode", "none"),
        "authorized_signatory_name": getattr(org, "authorized_signatory_name", ""),
        "show_computer_generated_disclaimer": getattr(org, "show_computer_generated_disclaimer", False),
    }
    
    bank = org.bank_accounts.filter(is_default=True).first()
    if not bank:
        bank = org.bank_accounts.first()
        
    if bank:
        company_dict.update({
            "bank_name": bank.bank_name,
            "acc_no": bank.account_number,
            "ifsc": bank.ifsc_code,
            "acc_name": bank.account_name,
            "branch": bank.branch,
        })

    return invoice_dict, customer_dict, items_list, company_dict
