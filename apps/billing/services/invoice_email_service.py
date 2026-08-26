"""
apps/billing/services/invoice_email_service.py

Production Email Delivery Service for Invoices in Advance Billing.
Renders invoice PDFs using the exact production PDF rendering pipeline
and emails them directly to the Organization Owner.
"""

import logging
import threading
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import close_old_connections
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from apps.billing.models import Invoice, EmailStatus, EmailTrigger
from apps.billing.services.pdf_adapter import invoice_to_pdf_dicts
from apps.invoices.services.bill_serializer import serialize_bill_for_render
from apps.invoices.services.invoice_preview_service import InvoicePreviewService
from apps.common.services.layout_engine import PrintableFrameBuilder
from apps.common.services.email_service import EmailBranding

logger = logging.getLogger(__name__)


class InvoiceEmailService:
    """
    Handles PDF generation, email composition, sending, audit logging,
    and background delivery of invoices to the Organization Owner.
    """

    @classmethod
    def generate_pdf_bytes(cls, invoice: Invoice, user=None) -> bytes:
        """
        Renders invoice PDF bytes using the EXACT production rendering pipeline
        used by Download and Preview functionality.
        """
        if user is None and invoice.organization:
            user = getattr(invoice.organization, "owner", None)

        # 1. Adapt ORM instance to canonical dictionaries
        invoice_dict, customer_dict, items_list, company_dict = invoice_to_pdf_dicts(invoice)

        # 2. Serialize canonical bill_data
        bill_data = serialize_bill_for_render(
            invoice=invoice_dict,
            customer=customer_dict,
            items=items_list,
            company=company_dict,
            org=invoice.organization,
        )

        # 3. Resolve PDF configuration
        config = InvoicePreviewService.resolve_render_config(user=user)

        # 4. Build printable layout frame geometry
        layout_frame = PrintableFrameBuilder.build_frame(invoice.organization, config)

        # 5. Resolve template file path
        template_file_path = InvoicePreviewService.resolve_template_path(config.get("template_name"))

        # 6. Render PDF bytes via WeasyPrint
        pdf_bytes = InvoicePreviewService.render_bill_pdf(
            bill_data=bill_data,
            config=config,
            template_file_path=template_file_path,
            layout_frame=layout_frame,
            org=invoice.organization,
        )

        return pdf_bytes

    @classmethod
    def get_recipient_email(cls, invoice: Invoice) -> str:
        """
        Resolves the Organization Owner's registered email address for an invoice.
        The recipient is ALWAYS the organization owner, NEVER the customer.
        """
        if invoice.organization and invoice.organization.owner and invoice.organization.owner.email:
            return invoice.organization.owner.email.strip()
        return ""

    @classmethod
    def send_invoice_email(cls, invoice: Invoice, trigger: str = EmailTrigger.MANUAL, user=None) -> tuple[bool, str]:
        """
        Sends the invoice PDF as an email attachment to the Organization Owner
        and updates audit delivery state.

        Parameters
        ----------
        invoice : Invoice instance
        trigger : 'automatic' or 'manual'
        user    : User initiating the request or None

        Returns
        -------
        (success: bool, message: str)
        """
        recipient_email = cls.get_recipient_email(invoice)

        if not recipient_email:
            error_msg = "The organization owner does not have a valid email address."
            invoice.email_last_status = EmailStatus.FAILED
            invoice.email_last_error = error_msg
            invoice.email_last_trigger = trigger
            invoice.save(update_fields=["email_last_status", "email_last_error", "email_last_trigger"])
            return False, error_msg

        # 1. Render PDF bytes
        try:
            pdf_bytes = cls.generate_pdf_bytes(invoice, user=user)
            if not pdf_bytes:
                raise ValueError("PDF rendering returned empty output.")
        except Exception as e:
            logger.error("PDF generation failure for Invoice %s: %s", invoice.invoice_number, str(e), exc_info=True)
            error_msg = "Failed to generate invoice PDF."
            invoice.email_last_status = EmailStatus.FAILED
            invoice.email_last_error = f"PDF Generation Error: {str(e)}"
            invoice.email_recipient = recipient_email
            invoice.email_last_trigger = trigger
            invoice.save(update_fields=["email_last_status", "email_last_error", "email_recipient", "email_last_trigger"])
            return False, error_msg

        # 2. Build email content
        org = invoice.organization
        owner = org.owner if org else None
        owner_name = ""
        if owner:
            owner_name = owner.get_full_name() or owner.first_name or owner.email.split("@")[0].capitalize()
        else:
            owner_name = "Organization Owner"

        org_name = org.business_name if org else "Advance Billing"
        inv_num = invoice.invoice_number or "Draft"
        subject = f"Invoice {inv_num} — Copy"

        inv_date_val = invoice.invoice_date
        if hasattr(inv_date_val, "strftime"):
            inv_date_str = inv_date_val.strftime("%b %d, %Y")
        else:
            inv_date_str = str(inv_date_val) if inv_date_val else ""

        due_date_str = None
        if invoice.due_date:
            if hasattr(invoice.due_date, "strftime"):
                due_date_str = invoice.due_date.strftime("%b %d, %Y")
            else:
                due_date_str = str(invoice.due_date)

        context = {
            "owner_name": owner_name,
            "org_name": org_name,
            "customer_name": invoice.customer_name_snapshot or (invoice.customer.name if invoice.customer else "Customer"),
            "invoice_number": inv_num,
            "invoice_date": inv_date_str,
            "due_date": due_date_str,
            "total_amount": f"{invoice.grand_total:,.2f}",
            "currency": invoice.currency or "INR",
            "app_name": getattr(settings, "APP_NAME", "Advance Billing"),
            "app_tagline": getattr(settings, "APP_TAGLINE", "GST Billing Made Simple for Indian Businesses"),
            "support_email": getattr(settings, "SERVER_EMAIL", "advancebillingbyvyom@gmail.com"),
        }
        context.update(EmailBranding.get_logo_context())

        # 3. Render HTML and Plain Text
        try:
            html_content = render_to_string("emails/invoice_email.html", context)
            text_content = strip_tags(html_content)

            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email],
            )
            email.attach_alternative(html_content, "text/html")

            # Attach PDF bytes directly (in-memory attachment, zero permanent storage)
            filename = f"Invoice_{inv_num}.pdf"
            email.attach(filename=filename, content=pdf_bytes, mimetype="application/pdf")

            # 4. Dispatch Email
            email.send(fail_silently=False)

            # 5. Audit Success Update
            invoice.email_sent = True
            invoice.email_last_sent_at = timezone.now()
            invoice.email_last_status = EmailStatus.SENT
            invoice.email_last_trigger = trigger
            invoice.email_last_error = ""
            invoice.email_recipient = recipient_email
            invoice.save(
                update_fields=[
                    "email_sent",
                    "email_last_sent_at",
                    "email_last_status",
                    "email_last_trigger",
                    "email_last_error",
                    "email_recipient",
                ]
            )

            logger.info("Invoice %s copy successfully emailed to owner %s", inv_num, recipient_email)
            return True, "Invoice copy emailed successfully to the organization owner."

        except Exception as e:
            logger.error("Failed to send email for Invoice %s to owner %s: %s", inv_num, recipient_email, str(e), exc_info=True)
            invoice.email_last_status = EmailStatus.FAILED
            invoice.email_last_error = str(e)
            invoice.email_recipient = recipient_email
            invoice.email_last_trigger = trigger
            invoice.save(
                update_fields=["email_last_status", "email_last_error", "email_recipient", "email_last_trigger"]
            )
            return False, "Failed to send invoice email to the organization owner. Please try again."

    @classmethod
    def send_invoice_email_async(cls, invoice_id: int, trigger: str = EmailTrigger.AUTOMATIC):
        """
        Asynchronously triggers invoice email delivery to the organization owner in a background worker thread.
        Receives invoice database ID to avoid using stale in-memory model instances.
        """
        import sys
        if getattr(settings, "TESTING", False) or "test" in sys.argv:
            try:
                invoice = Invoice.objects.select_related("organization", "organization__owner", "customer").get(id=invoice_id)
                cls.send_invoice_email(invoice, trigger=trigger)
            except Exception as e:
                logger.error("Background invoice email delivery error for invoice id %s: %s", invoice_id, str(e), exc_info=True)
            return None

        def worker():
            close_old_connections()
            try:
                invoice = Invoice.objects.select_related("organization", "organization__owner", "customer").get(id=invoice_id)
                cls.send_invoice_email(invoice, trigger=trigger)
            except Exception as e:
                logger.error("Background invoice email delivery error for invoice id %s: %s", invoice_id, str(e), exc_info=True)
            finally:
                close_old_connections()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        return thread
