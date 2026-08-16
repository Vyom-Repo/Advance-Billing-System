import logging
from decimal import Decimal
from django.core.exceptions import ValidationError

from apps.products.models import TaxabilityType, PriceBasis, CessType
from apps.billing.models import InvoiceLine, Invoice
from apps.billing.services.pricing import (
    calculate_gross_line_value,
    calculate_discount_amount,
    calculate_net_line_value,
    calculate_tax_exclusive_base_from_inclusive,
    quantize_money
)

logger = logging.getLogger(__name__)

def _normalize_state_code(code: str) -> str:
    """Safely extracts and upper-cases a state code string."""
    return (code or "").strip().upper()

def calculate_line_tax(line: InvoiceLine, supplier_state_code: str, place_of_supply: str) -> dict:
    """
    Calculates the GST tax result for a single InvoiceLine, consuming its snapshot values
    and the net transaction value (from Phase 06 pricing).

    Args:
        line: The InvoiceLine to calculate taxes for.
        supplier_state_code: The organization's state code.
        place_of_supply: The invoice's Place of Supply (must be formatted identically to supplier_state_code).

    Returns:
        dict: A structured dictionary of the tax components and amounts.
    """
    supplier_code = _normalize_state_code(supplier_state_code)
    pos = _normalize_state_code(place_of_supply)

    if not pos:
        raise ValidationError("Place of supply cannot be blank for GST calculation.")
    
    is_intra_state = (supplier_code == pos)

    # 1. Base Pricing from Phase 06
    gross_value = calculate_gross_line_value(Decimal(str(line.quantity)), line.unit_price)
    discount_amount = calculate_discount_amount(gross_value, line.discount_type, line.discount_value)
    net_transaction_value = calculate_net_line_value(gross_value, discount_amount)
    taxable_value = net_transaction_value
    cgst_rate = Decimal('0.00')
    cgst_amount = Decimal('0.00')
    sgst_rate = Decimal('0.00')
    sgst_amount = Decimal('0.00')
    igst_rate = Decimal('0.00')
    igst_amount = Decimal('0.00')
    cess_amount = Decimal('0.00')
    total_gst = Decimal('0.00')
    total_tax = Decimal('0.00')

    # 2. Taxability handling
    if line.taxability_type_snapshot == TaxabilityType.TAXABLE:
        gst_rate = quantize_money(line.gst_rate_snapshot)
        
        # 3. Inclusive Price Extraction
        if line.price_basis_snapshot == PriceBasis.INCLUSIVE:
            taxable_value = calculate_tax_exclusive_base_from_inclusive(net_transaction_value, gst_rate)
        
        # 4. GST Components Calculation
        if is_intra_state:
            cgst_rate = gst_rate / Decimal('2.00')
            sgst_rate = gst_rate / Decimal('2.00')
            cgst_amount = quantize_money(taxable_value * (cgst_rate / Decimal('100.00')))
            sgst_amount = quantize_money(taxable_value * (sgst_rate / Decimal('100.00')))
            total_gst = cgst_amount + sgst_amount
        else:
            igst_rate = gst_rate
            igst_amount = quantize_money(taxable_value * (igst_rate / Decimal('100.00')))
            total_gst = igst_amount

    # 5. Cess Calculation (Kept separate from GST)
    if line.cess_applicable_snapshot:
        if line.cess_type_snapshot == CessType.PERCENTAGE:
            c_rate = line.cess_rate_snapshot or Decimal('0.00')
            cess_amount = quantize_money(taxable_value * (c_rate / Decimal('100.00')))
        elif line.cess_type_snapshot == CessType.FIXED_AMOUNT:
            # Per unit cess amount derived from product snapshot model semantics
            c_amount_per_unit = line.cess_rate_snapshot or Decimal('0.00')
            cess_amount = quantize_money(c_amount_per_unit * Decimal(str(line.quantity)))

    total_tax = total_gst + cess_amount

    return {
        "taxability_type": line.taxability_type_snapshot,
        "price_basis": line.price_basis_snapshot,
        "taxable_value": quantize_money(taxable_value),
        "gst_rate": quantize_money(line.gst_rate_snapshot) if line.taxability_type_snapshot == TaxabilityType.TAXABLE else Decimal('0.00'),
        "cgst_rate": quantize_money(cgst_rate),
        "cgst_amount": quantize_money(cgst_amount),
        "sgst_rate": quantize_money(sgst_rate),
        "sgst_amount": quantize_money(sgst_amount),
        "igst_rate": quantize_money(igst_rate),
        "igst_amount": quantize_money(igst_amount),
        "cess_amount": quantize_money(cess_amount),
        "reverse_charge": line.reverse_charge_snapshot,
        "total_gst": quantize_money(total_gst),
        "total_tax": quantize_money(total_tax),
    }

def aggregate_invoice_taxes(invoice: Invoice, supplier_state_code: str) -> dict:
    """
    Aggregates the total taxes for an invoice by calculating tax on each line.
    
    Args:
        invoice: The Invoice model instance.
        supplier_state_code: The organization's state code.
        
    Returns:
        dict: A structured dictionary of aggregated tax totals.
    """
    total_taxable_value = Decimal('0.00')
    total_cgst = Decimal('0.00')
    total_sgst = Decimal('0.00')
    total_igst = Decimal('0.00')
    total_cess = Decimal('0.00')
    total_gst = Decimal('0.00')
    total_tax = Decimal('0.00')
    
    place_of_supply = invoice.place_of_supply

    for line in invoice.lines.all():
        line_tax = calculate_line_tax(line, supplier_state_code, place_of_supply)
        
        total_taxable_value += line_tax["taxable_value"]
        total_cgst += line_tax["cgst_amount"]
        total_sgst += line_tax["sgst_amount"]
        total_igst += line_tax["igst_amount"]
        total_cess += line_tax["cess_amount"]
        total_gst += line_tax["total_gst"]
        total_tax += line_tax["total_tax"]
        
    return {
        "total_taxable_value": quantize_money(total_taxable_value),
        "total_cgst": quantize_money(total_cgst),
        "total_sgst": quantize_money(total_sgst),
        "total_igst": quantize_money(total_igst),
        "total_cess": quantize_money(total_cess),
        "total_gst": quantize_money(total_gst),
        "total_tax": quantize_money(total_tax)
    }
