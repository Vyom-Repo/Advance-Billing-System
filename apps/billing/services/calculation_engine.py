from decimal import Decimal, ROUND_HALF_UP
import logging
from django.db import transaction
from django.core.exceptions import ValidationError

from apps.billing.models import Invoice, InvoiceLine
from apps.billing.services.pricing import (
    calculate_gross_line_value,
    calculate_discount_amount,
    calculate_net_line_value,
    quantize_money
)
from apps.billing.services.gst_engine import calculate_line_tax
from apps.billing.services.lifecycle import prepare_invoice_snapshots, issue_invoice
from apps.products.models import TaxabilityType, PriceBasis

logger = logging.getLogger(__name__)

def validate_invoice(invoice: Invoice):
    """
    Validates that the invoice is ready for calculation and issuance.
    """
    if not invoice.customer:
        raise ValidationError("Customer is required to finalize the invoice.")
    
    if invoice.customer.organization_id != invoice.organization_id:
        raise ValidationError("Customer does not belong to the invoice's organization.")
    
    if not invoice.place_of_supply:
        raise ValidationError("Place of Supply is required.")
        
    lines = list(invoice.lines.all())
    if not lines:
        raise ValidationError("Invoice must contain at least one line.")
        
    for line in lines:
        if not line.product:
            raise ValidationError(f"Product is missing on line {line.position}.")
        if line.product.organization_id != invoice.organization_id:
            raise ValidationError(f"Product on line {line.position} does not belong to the invoice's organization.")
        if line.quantity <= 0:
            raise ValidationError(f"Quantity must be greater than zero on line {line.position}.")
        if line.unit_price is None or line.unit_price < 0:
            raise ValidationError(f"Unit price must be zero or positive on line {line.position}.")


def calculate_line(line: InvoiceLine, supplier_state_code: str, place_of_supply: str) -> dict:
    """
    Calculates Phase 06 pricing and Phase 07 GST for a single line.
    Returns a dict with line-level calculated values.
    """
    # Phase 06 Pricing
    gross = calculate_gross_line_value(Decimal(str(line.quantity)), line.unit_price)
    discount_amount = calculate_discount_amount(gross, line.discount_type, line.discount_value)
    net_transaction_value = calculate_net_line_value(gross, discount_amount)
    
    # Update line in memory for GST engine which consumes the line object
    line.discount_amount = discount_amount
    
    # Phase 07 GST (uses snapshot fields populated in memory)
    tax_result = calculate_line_tax(line, supplier_state_code, place_of_supply)
    
    # Calculate Line Total based on Price Basis
    if line.price_basis_snapshot == PriceBasis.INCLUSIVE:
        # Inclusive price: net_transaction_value already contains GST
        line_total = net_transaction_value
    else:
        # Exclusive price
        if line.taxability_type_snapshot == TaxabilityType.TAXABLE:
            # Add tax and cess to the pre-tax base
            line_total = net_transaction_value + tax_result["total_tax"]
        else:
            # Exempt/Nil-rated/Non-GST: No tax to add
            line_total = net_transaction_value

    line.taxable_value = tax_result["taxable_value"]
    line.cgst_amount = tax_result["cgst_amount"]
    line.sgst_amount = tax_result["sgst_amount"]
    line.igst_amount = tax_result["igst_amount"]
    line.cess_amount = tax_result["cess_amount"]
    line.line_total = quantize_money(line_total)

    # Return for aggregation
    return {
        "gross": gross,
        "discount": discount_amount,
        "taxable_value": tax_result["taxable_value"],
        "cgst": tax_result["cgst_amount"],
        "sgst": tax_result["sgst_amount"],
        "igst": tax_result["igst_amount"],
        "cess": tax_result["cess_amount"],
        "total_tax": tax_result["total_tax"],
        "net_transaction_value": net_transaction_value
    }

def calculate_invoice(invoice: Invoice, lines: list) -> dict:
    """
    Aggregates all lines and calculates Invoice totals.
    """
    supplier_state_code = invoice.organization.state_code
    place_of_supply = invoice.place_of_supply
    
    subtotal = Decimal('0.00')
    discount_total = Decimal('0.00')
    taxable_amount = Decimal('0.00')
    cgst_total = Decimal('0.00')
    sgst_total = Decimal('0.00')
    igst_total = Decimal('0.00')
    cess_total = Decimal('0.00')
    total_tax = Decimal('0.00')
    net_total = Decimal('0.00')

    pre_round_total = Decimal('0.00')

    for line in lines:
        res = calculate_line(line, supplier_state_code, place_of_supply)
        
        subtotal += res["gross"]
        discount_total += res["discount"]
        taxable_amount += res["taxable_value"]
        cgst_total += res["cgst"]
        sgst_total += res["sgst"]
        igst_total += res["igst"]
        cess_total += res["cess"]
        total_tax += res["total_tax"]
        net_total += res["net_transaction_value"]
        
        # Calculate pre-round total correctly avoiding double-counting inclusive tax
        if line.price_basis_snapshot == PriceBasis.INCLUSIVE:
            pre_round_total += res["net_transaction_value"]
        else:
            if line.taxability_type_snapshot == TaxabilityType.TAXABLE:
                pre_round_total += (res["net_transaction_value"] + res["total_tax"])
            else:
                pre_round_total += res["net_transaction_value"]

    invoice.subtotal = subtotal
    invoice.discount_total = discount_total
    invoice.taxable_amount = taxable_amount
    invoice.cgst_total = cgst_total
    invoice.sgst_total = sgst_total
    invoice.igst_total = igst_total
    invoice.cess_total = cess_total
    
    # Calculate Round Off (nearest whole number)
    grand_total_unrounded = pre_round_total
    grand_total_rounded = grand_total_unrounded.quantize(Decimal('1.'), rounding=ROUND_HALF_UP)
    round_off = grand_total_rounded - grand_total_unrounded
    
    invoice.round_off = quantize_money(round_off)
    invoice.grand_total = quantize_money(grand_total_rounded)
    
    return {
        "subtotal": subtotal,
        "grand_total": invoice.grand_total
    }

@transaction.atomic
def finalize_invoice(invoice: Invoice) -> Invoice:
    """
    The authoritative transaction pipeline for calculation, validation, and issuance.
    """
    # 1. Validate inputs
    validate_invoice(invoice)
    
    # 2. Prepare snapshots in memory
    lines = prepare_invoice_snapshots(invoice)
    
    # 3. Calculate pricing & GST & Aggregation & Round-off
    calculate_invoice(invoice, lines)
    
    # 4. Persist InvoiceLine calculations + snapshots
    for line in lines:
        line.save(update_fields=[
            'product_name_snapshot',
            'product_type_snapshot',
            'hsn_sac_snapshot',
            'taxability_type_snapshot',
            'gst_rate_snapshot',
            'cess_applicable_snapshot',
            'cess_type_snapshot',
            'cess_rate_snapshot',
            'reverse_charge_snapshot',
            'price_basis_snapshot',
            'uqc_snapshot',
            
            'discount_amount',
            'taxable_value',
            'cgst_amount',
            'sgst_amount',
            'igst_amount',
            'cess_amount',
            'line_total'
        ])
    
    # 5. Persist Invoice calculations + snapshots
    invoice.save(update_fields=[
        'customer_name_snapshot',
        'customer_gstin_snapshot',
        'customer_billing_address_snapshot',
        'customer_state_code_snapshot',
        
        'subtotal',
        'discount_total',
        'taxable_amount',
        'cgst_total',
        'sgst_total',
        'igst_total',
        'cess_total',
        'round_off',
        'grand_total'
    ])
    
    # 6. Issue Invoice (allocate number and lock)
    return issue_invoice(invoice)
