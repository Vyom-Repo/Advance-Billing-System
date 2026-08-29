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


class _BoundedInvoiceEmailExecutor:
    """
    Process-local bounded worker executor for background invoice email delivery.
    Enforces a maximum of MAX_WORKERS (2) concurrent daemon threads per application process
    and a bounded queue capacity of MAX_QUEUE_SIZE (100).
    """
    MAX_WORKERS = 2
    MAX_QUEUE_SIZE = 100

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """Thread-safe singleton getter."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        import queue
        self._queue = queue.Queue(maxsize=self.MAX_QUEUE_SIZE)
        self._pending_ids = set()
        self._lock = threading.Lock()
        self._workers = []
        self._started = False

    def _start_workers_if_needed(self):
        """Thread-safe initialization of worker daemon threads (max 2 per process)."""
        if not self._started:
            with self._lock:
                if not self._started:
                    for i in range(self.MAX_WORKERS):
                        worker_thread = threading.Thread(
                            target=self._worker_loop,
                            daemon=True,
                            name=f"InvoiceEmailWorker-{i+1}"
                        )
                        worker_thread.start()
                        self._workers.append(worker_thread)
                    self._started = True

    def _worker_loop(self):
        """Worker thread processing loop with DB connection cleanup and error isolation."""
        from django.db.utils import OperationalError
        import time

        while True:
            try:
                invoice_id, trigger = self._queue.get()
            except Exception:
                break

            logger.info("Invoice email job started for invoice ID %s", invoice_id)
            close_old_connections()
            try:
                invoice = None
                for attempt in range(5):
                    try:
                        invoice = Invoice.objects.select_related(
                            "organization", "organization__owner", "customer"
                        ).get(id=invoice_id)
                        break
                    except OperationalError as oe:
                        if "locked" in str(oe).lower() and attempt < 4:
                            time.sleep(0.05)
                            continue
                        raise

                if invoice is not None:
                    org_id = invoice.organization_id if invoice.organization else None
                    owner = invoice.organization.owner if (invoice.organization and invoice.organization.owner) else None
                    success, msg = InvoiceEmailService.send_invoice_email(invoice, trigger=trigger, user=owner)
                    if success:
                        logger.info("Invoice email job completed for invoice ID %s (org ID %s)", invoice_id, org_id)
                    else:
                        logger.error("Invoice email job failed for invoice ID %s (org ID %s): %s", invoice_id, org_id, msg)
            except Exception as e:
                logger.error("Invoice email job failed with exception for invoice ID %s: %s", invoice_id, str(e), exc_info=True)
            finally:
                with self._lock:
                    self._pending_ids.discard(invoice_id)
                close_old_connections()
                self._queue.task_done()

    def submit(self, invoice_id: int, trigger: str = EmailTrigger.AUTOMATIC) -> bool:
        """
        Enqueues an invoice email job if not already pending/executing and queue has capacity.
        Returns True if queued, False if duplicate or queue full.
        """
        self._start_workers_if_needed()

        with self._lock:
            if invoice_id in self._pending_ids:
                logger.info("Invoice email job for invoice ID %s is already pending or executing. Duplicate job ignored.", invoice_id)
                return False

            if self._queue.full():
                logger.warning(
                    "Invoice email queue full (%s items). Rejected job for invoice ID %s.",
                    self.MAX_QUEUE_SIZE,
                    invoice_id,
                )
                return False

            self._pending_ids.add(invoice_id)
            self._queue.put_nowait((invoice_id, trigger))
            logger.info("Invoice email job for invoice ID %s queued successfully.", invoice_id)
            return True


    def flush(self):
        """Waits for all currently enqueued items in the queue to be processed by worker threads."""
        self._queue.join()


class InvoiceEmailService:
    """
    Handles PDF generation, email composition, sending, audit logging,
    and background delivery of invoices to the Organization Owner.
    """

    @classmethod
    def generate_pdf_bytes(cls, invoice: Invoice, user=None) -> bytes:
        """
        Renders invoice PDF bytes using the EXACT canonical rendering pipeline
        used by Download and Preview functionality.
        """
        return InvoicePreviewService.render_invoice_to_pdf(invoice, user=user)

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
            inv_date_str = inv_date_val.strftime("%d/%m/%Y")
        else:
            inv_date_str = str(inv_date_val) if inv_date_val else ""

        due_date_str = None
        if invoice.due_date:
            if hasattr(invoice.due_date, "strftime"):
                due_date_str = invoice.due_date.strftime("%d/%m/%Y")
            else:
                due_date_str = str(invoice.due_date)

        from apps.common.services.email_service import AdvanceBillingEmailBranding  # noqa: PLC0415
        email_branding = AdvanceBillingEmailBranding.get_email_branding()

        context = {
            "email_branding": email_branding,
            "branding": email_branding,
            "owner_name": owner_name,
            "org_name": org_name,
            "customer_name": invoice.customer_name_snapshot or (invoice.customer.name if invoice.customer else "Customer"),
            "invoice_number": inv_num,
            "invoice_date": inv_date_str,
            "due_date": due_date_str,
            "total_amount": f"{invoice.grand_total:,.2f}",
            "currency": invoice.currency or "INR",
            "app_name": email_branding["app_name"],
            "app_tagline": email_branding["tagline"],
            "support_email": email_branding["support_email"],
        }

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

            # 4. Dispatch Email (simulated safely in Demo Mode)
            if getattr(org.owner, "username", "") == "demo_user" or (user and getattr(user, "username", "") == "demo_user"):
                logger.info("Demo Mode: Simulated email sending for invoice %s", inv_num)
            else:
                logger.info(
                    "Effective SMTP config: host=%s port=%s use_tls=%s use_ssl=%s timeout=%s backend=%s",
                    getattr(settings, "EMAIL_HOST", ""),
                    getattr(settings, "EMAIL_PORT", ""),
                    getattr(settings, "EMAIL_USE_TLS", ""),
                    getattr(settings, "EMAIL_USE_SSL", ""),
                    getattr(settings, "EMAIL_TIMEOUT", ""),
                    getattr(settings, "EMAIL_BACKEND", ""),
                )
                logger.info("Starting SMTP send for invoice %s using EMAIL_BACKEND: %s", inv_num, getattr(settings, "EMAIL_BACKEND", ""))
                send_res = email.send(fail_silently=False)
                logger.info("SMTP send completed for invoice %s (result=%s)", inv_num, send_res)

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
            logger.error("SMTP send failed for invoice %s: %s — %s", inv_num, type(e).__name__, str(e), exc_info=True)
            invoice.email_last_status = EmailStatus.FAILED
            invoice.email_last_error = str(e)
            invoice.email_recipient = recipient_email
            invoice.email_last_trigger = trigger
            invoice.save(
                update_fields=["email_last_status", "email_last_error", "email_recipient", "email_last_trigger"]
            )
            return False, "Failed to send invoice email to the organization owner. Please try again."

    @classmethod
    def send_invoice_email_async(cls, invoice_id: int, trigger: str = EmailTrigger.AUTOMATIC) -> bool:
        """
        Submits invoice email delivery for background execution using the process-level bounded executor.
        In Django test runner mode, executes synchronously to support SQLite single-thread savepoint locks.
        """
        import sys
        if getattr(settings, "TESTING", False) or "test" in sys.argv:
            try:
                invoice = Invoice.objects.select_related("organization", "organization__owner", "customer").get(id=invoice_id)
                cls.send_invoice_email(invoice, trigger=trigger)
                return True
            except Exception as e:
                logger.error("Background invoice email delivery error for invoice id %s: %s", invoice_id, str(e), exc_info=True)
                return False

        executor = _BoundedInvoiceEmailExecutor.get_instance()
        return executor.submit(invoice_id, trigger=trigger)
