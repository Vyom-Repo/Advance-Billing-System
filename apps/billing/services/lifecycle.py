from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus
from apps.settings_app.models import InvoicePreference


def populate_line_snapshot(line: InvoiceLine) -> None:
    """
    Copies product master attributes into InvoiceLine snapshot fields so the
    row can be persisted as a valid Draft without running the full finalization
    pipeline.

    Responsibility split:
        populate_line_snapshot() — called at Draft save; keeps the row valid.
        prepare_invoice_snapshots() / finalize_invoice() — called at Issue;
            re-freezes the authoritative historical snapshot.

    This function mutates `line` in-place and does NOT call line.save().
    """
    if not line.product:
        raise ValidationError(
            f"Cannot populate snapshot for line at position {line.position}: "
            "product is not set."
        )
    snap = line.product.as_invoice_snapshot()
    line.product_name_snapshot    = snap["product_name"]
    line.product_type_snapshot    = snap["product_type"]
    line.hsn_sac_snapshot         = snap["classification_code"] or ""
    line.taxability_type_snapshot = snap["taxability_type"]
    line.gst_rate_snapshot        = Decimal(snap["gst_rate"])
    line.cess_applicable_snapshot = snap["cess_applicable"]
    line.cess_type_snapshot       = snap["cess_type"]
    line.cess_rate_snapshot       = (
        Decimal(snap["cess_rate_or_amount"])
        if snap["cess_rate_or_amount"] is not None
        else None
    )
    line.reverse_charge_snapshot  = snap["reverse_charge_applicable"]
    line.price_basis_snapshot     = snap["price_basis"]
    line.uqc_snapshot             = snap["uqc"]


def resolve_place_of_supply(
    shipping_same_as_billing: bool,
    shipping_state_code: str,
    customer,
) -> str:
    """
    Derives the canonical 2-digit GST Place of Supply state code.

    Logic:
        shipping_same_as_billing=True  → customer.billing_state_code
        shipping_same_as_billing=False → shipping_state_code (user-selected from dropdown)

    The caller is responsible for passing a valid 2-digit state code.
    This function validates that the resulting code is in the canonical state
    list and raises ValidationError if it is not.

    This is the single authoritative source of truth for place_of_supply
    derivation.  It is intentionally pure (no DB access) so it can be called
    from any context (view, test, service) without side effects.
    """
    from apps.organization.services import LocalGSTValidator

    if shipping_same_as_billing:
        pos = (customer.billing_state_code or "").strip()
    else:
        pos = (shipping_state_code or "").strip()

    if not pos:
        raise ValidationError(
            "Place of Supply could not be determined. "
            "Please ensure the billing or shipping state is set correctly."
        )
    if pos not in LocalGSTValidator.STATE_CODES:
        raise ValidationError(
            f"Invalid state code '{pos}' for Place of Supply. "
            "Please select a valid state."
        )
    return pos


def prepare_invoice_snapshots(invoice: Invoice, lines: list = None) -> list:
    """
    Mutates the invoice and its lines in memory to populate historical snapshot fields.
    Does not save to the database.
    Returns the list of mutated lines.
    """
    if not invoice.customer:
        raise ValidationError("Cannot prepare snapshots without a customer.")
    
    if invoice.customer.organization_id != invoice.organization_id:
        raise ValidationError("Customer does not belong to the invoice's organization.")

    # Populate customer snapshots
    invoice.customer_name_snapshot = invoice.customer.name
    invoice.customer_gstin_snapshot = invoice.customer.gstin or ""
    invoice.customer_billing_address_snapshot = invoice.customer.full_billing_address
    invoice.customer_state_code_snapshot = invoice.customer.billing_state_code

    if lines is None:
        lines = list(invoice.lines.all())
        
    for line in lines:
        if not line.product:
            raise ValidationError(f"Cannot prepare snapshots. Line at position {line.position} is missing a product.")
        
        if line.product.organization_id != invoice.organization_id:
            raise ValidationError(f"Product on line {line.position} does not belong to the invoice's organization.")
        
        snap = line.product.as_invoice_snapshot()
        line.product_name_snapshot = snap["product_name"]
        line.product_type_snapshot = snap["product_type"]
        line.hsn_sac_snapshot = snap["classification_code"] or ""
        line.taxability_type_snapshot = snap["taxability_type"]
        line.gst_rate_snapshot = Decimal(snap["gst_rate"])
        line.cess_applicable_snapshot = snap["cess_applicable"]
        line.cess_type_snapshot = snap["cess_type"]
        if snap["cess_rate_or_amount"] is not None:
            line.cess_rate_snapshot = Decimal(snap["cess_rate_or_amount"])
        else:
            line.cess_rate_snapshot = None
        line.reverse_charge_snapshot = snap["reverse_charge_applicable"]
        line.price_basis_snapshot = snap["price_basis"]
        line.uqc_snapshot = snap["uqc"]

    return lines


@transaction.atomic
def issue_invoice(invoice: Invoice) -> Invoice:
    """
    Transitions a Draft invoice to Issued status, atomically assigning a unique invoice number.
    Ensures organization scoping and atomicity using row-level locking on InvoicePreference.
    """
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValidationError("Only draft invoices can be issued.")
        
    # Defensively ensure required snapshots exist
    if not invoice.customer_name_snapshot:
        raise ValidationError("Invoice customer snapshot is missing. Snapshots must be prepared and saved before issuing.")

    # Lock the preference row for this organization to guarantee atomic number allocation.
    # Safely initialize InvoicePreference if it does not exist yet.
    try:
        pref = InvoicePreference.objects.select_for_update().get(user=invoice.organization.owner)
    except InvoicePreference.DoesNotExist:
        InvoicePreference.objects.get_or_create(user=invoice.organization.owner)
        pref = InvoicePreference.objects.select_for_update().get(user=invoice.organization.owner)
    
    # Generate number using the locked preference state
    prefix = (pref.invoice_prefix or "").strip().upper()
    fy_str = "2026-27" if pref.include_financial_year else ""
    num_str = str(pref.starting_number).zfill(4)
    
    parts = []
    if prefix:
        parts.append(prefix)
    if fy_str:
        parts.append(fy_str)
    parts.append(num_str)
    
    invoice_num = "-".join(parts)
    
    # Update and save invoice
    invoice.invoice_number = invoice_num
    invoice.status = InvoiceStatus.ISSUED
    invoice.save(update_fields=['invoice_number', 'status'])
    
    # Atomically increment the sequence and save
    pref.starting_number += 1
    pref.save(update_fields=['starting_number'])

    # Register post-commit automatic email delivery to organization owner
    inv_id = invoice.id
    def trigger_auto_email():
        from apps.billing.services.invoice_email_service import InvoiceEmailService, EmailTrigger
        InvoiceEmailService.send_invoice_email_async(inv_id, trigger=EmailTrigger.AUTOMATIC)

    transaction.on_commit(trigger_auto_email)
    
    return invoice

@transaction.atomic
def cancel_invoice(invoice: Invoice) -> Invoice:
    """
    Transitions an Issued invoice to Cancelled status.
    The invoice remains in the database for historical retention.
    """
    if invoice.status != InvoiceStatus.ISSUED:
        raise ValidationError("Only issued invoices can be cancelled.")
    
    invoice.status = InvoiceStatus.CANCELLED
    invoice.save(update_fields=['status'])
    return invoice

@transaction.atomic
def delete_invoice(invoice: Invoice):
    """
    Deletes a Draft invoice. Issued or Cancelled invoices cannot be deleted.
    """
    if invoice.status != InvoiceStatus.DRAFT:
        raise ValidationError("Issued or cancelled invoices cannot be deleted.")
    
    invoice.delete()
