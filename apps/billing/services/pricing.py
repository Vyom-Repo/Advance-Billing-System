"""
apps/billing/services/pricing.py — Pricing Engine Service

This service establishes the transactional pricing truth for Advance Billing.
It strictly operates on Decimal and handles:
- Deterministic quantization.
- Gross calculation.
- Discount validation and calculation.
- Net transaction values.
- Inclusive price decomposition utilities.
- Invoice-level aggregation (returning data, not saving to the DB).
"""

from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from apps.billing.models import Invoice, DiscountType

# Consistent quantization strategy for all monetary calculations.
MONEY_QUANTIZER = Decimal("0.01")

def quantize_money(amount: Decimal) -> Decimal:
    """
    Rounds a given decimal amount to 2 decimal places using ROUND_HALF_UP.
    Raises ValidationError if amount is not a Decimal.
    """
    if not isinstance(amount, Decimal):
        raise ValidationError("Monetary calculations require Decimal types.")
    return amount.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def calculate_gross_line_value(quantity: Decimal, unit_price: Decimal) -> Decimal:
    """
    Calculates the gross line value (Quantity * Unit Price).
    Validates that quantity and unit_price are non-negative.
    """
    if not isinstance(quantity, Decimal) or not isinstance(unit_price, Decimal):
        raise ValidationError("Quantity and unit_price must be Decimals.")

    if quantity < 0:
        raise ValidationError("Quantity cannot be negative.")
    
    if unit_price < 0:
        raise ValidationError("Unit price cannot be negative.")

    gross = quantity * unit_price
    return quantize_money(gross)


def calculate_discount_amount(gross: Decimal, discount_type: str, discount_value: Decimal) -> Decimal:
    """
    Calculates the discount amount based on the discount type and gross value.
    Validates logical bounds (e.g. 0-100% or 0-Gross).
    """
    if not isinstance(gross, Decimal) or not isinstance(discount_value, Decimal):
        raise ValidationError("Gross and discount_value must be Decimals.")

    if discount_value < 0:
        raise ValidationError("Discount value cannot be negative.")

    if discount_type == DiscountType.PERCENTAGE:
        if discount_value > Decimal("100.00"):
            raise ValidationError("Percentage discount cannot exceed 100%.")
        discount_amount = gross * (discount_value / Decimal("100"))
        
    elif discount_type == DiscountType.FIXED:
        if discount_value > gross:
            raise ValidationError("Fixed discount cannot exceed the gross line value.")
        discount_amount = discount_value

    elif discount_type == DiscountType.NONE:
        discount_amount = Decimal("0.00")
        
    else:
        raise ValidationError(f"Unknown discount type: {discount_type}")

    return quantize_money(discount_amount)


def calculate_net_line_value(gross: Decimal, discount_amount: Decimal) -> Decimal:
    """
    Calculates the net transaction value (Gross - Discount Amount).
    """
    if not isinstance(gross, Decimal) or not isinstance(discount_amount, Decimal):
        raise ValidationError("Inputs must be Decimals.")
        
    if discount_amount > gross:
        raise ValidationError("Discount amount cannot exceed gross value.")
        
    net = gross - discount_amount
    return quantize_money(net)


def calculate_tax_exclusive_base_from_inclusive(net_value: Decimal, gst_rate: Decimal) -> Decimal:
    """
    A pure mathematical utility that decomposes a GST-inclusive amount into 
    its pre-tax base, given a specific GST rate.
    
    This does NOT decide which GST rate applies; Phase 07 owns tax engine rules.
    """
    if not isinstance(net_value, Decimal) or not isinstance(gst_rate, Decimal):
        raise ValidationError("Inputs must be Decimals.")
        
    if gst_rate < Decimal("0.00"):
        raise ValidationError("GST rate cannot be negative.")

    if gst_rate == Decimal("0.00"):
        return quantize_money(net_value)

    base = net_value * (Decimal("100.00") / (Decimal("100.00") + gst_rate))
    return quantize_money(base)


def calculate_invoice_pricing_summary(invoice: Invoice) -> dict:
    """
    Aggregates all lines for a given invoice and returns a summary dictionary.
    Does NOT save to the database.
    """
    gross_subtotal = Decimal("0.00")
    total_discount = Decimal("0.00")
    net_transaction_value = Decimal("0.00")

    for line in invoice.lines.all():
        gross = calculate_gross_line_value(line.quantity, line.unit_price)
        discount = calculate_discount_amount(gross, line.discount_type, line.discount_value)
        net = calculate_net_line_value(gross, discount)

        gross_subtotal += gross
        total_discount += discount
        net_transaction_value += net

    return {
        "gross_subtotal": quantize_money(gross_subtotal),
        "total_discount": quantize_money(total_discount),
        "net_transaction_value": quantize_money(net_transaction_value),
    }
