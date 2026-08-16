"""
apps/billing/services/pdf_adapter.py

Adapts Phase 08 Invoice ORM instances into the simple dictionaries required
by the existing Phase 01 PDF serialization pipeline (bill_serializer.py).

This adapter is entirely side-effect free and performs no calculations.
"""

from apps.billing.models import Invoice

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
        "date": invoice.invoice_date,
        "due_date": invoice.due_date,
        "place_of_supply": invoice.place_of_supply,
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
    customer_dict = {
        "name": invoice.customer_name_snapshot,
        "gstin": invoice.customer_gstin_snapshot,
        "address": invoice.customer_billing_address_snapshot,
        "state_code": invoice.customer_state_code_snapshot,
        
        "shipping_name": invoice.customer_name_snapshot,
        "shipping_address": invoice.shipping_address_line_1,
        "shipping_city": invoice.shipping_city,
        "shipping_state": invoice.shipping_state,
        "shipping_pincode": invoice.shipping_pincode,
    }

    # 3. Items List
    items_list = []
    for line in invoice.lines.all().order_by('position'):
        items_list.append({
            "name": line.product_name_snapshot,
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
