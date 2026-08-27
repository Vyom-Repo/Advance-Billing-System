"""
apps/billing/tests/test_bounded_email_worker.py

Focused tests for Phase 1: Bounded Invoice Email Worker.
Verifies bounded concurrency (<= 2), queue capacity (100), queue overflow rejection,
duplicate protection, pending_ids cleanup on success and failure, failure isolation,
and transaction safety.
"""

import time
import threading
from unittest import mock
from django.test import TransactionTestCase
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.billing.models import Invoice, InvoiceStatus, EmailTrigger
from apps.billing.services.lifecycle import issue_invoice, prepare_invoice_snapshots
from apps.billing.services.invoice_email_service import (
    InvoiceEmailService,
    _BoundedInvoiceEmailExecutor,
)
from apps.organization.models import Organization, BankAccount
from apps.customers.models import Customer, GSTStatus
from apps.products.models import Product

User = get_user_model()


class BoundedEmailWorkerTest(TransactionTestCase):
    """
    Unit tests for _BoundedInvoiceEmailExecutor thread pool, queue limits, and duplicate protection.
    Uses TransactionTestCase to support multi-threaded SQLite access without database table locking.
    """

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="testowner",
            email="owner@example.com",
            password="Password123!"
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Test Business",
            business_email="owner@example.com",
            address_line_1="123 Street",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            state_code="27",
            is_gst_registered=True,
            gstin="27ABCDE1234F1Z5"
        )
        BankAccount.objects.create(
            organization=self.org,
            bank_name="Test Bank",
            account_name="Test Business",
            account_number="1234567890",
            ifsc_code="SBIN0001234",
            branch="Main Branch",
            is_default=True
        )
        self.customer = Customer.objects.create(
            organization=self.org,
            name="Test Customer",
            gst_status=GSTStatus.UNREGISTERED,
            billing_address_line_1="123 Main St",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_state_code="27",
            billing_pin_code="400001"
        )
        self.product = Product.objects.create(
            organization=self.org,
            name="Widget A",
            unit_price=100.00,
            hsn_code="8471",
            gst_rate=18.00
        )
        self.invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=timezone.now().date(),
            place_of_supply="27",
            subtotal=100.00,
            grand_total=118.00,
            status=InvoiceStatus.DRAFT
        )

    def tearDown(self):
        executor = _BoundedInvoiceEmailExecutor.get_instance()
        executor._queue.join()
        with executor._lock:
            executor._pending_ids.clear()
        super().tearDown()

    def test_01_normal_invoice_email_job_queued_and_processed(self):
        """Test 1: Normal invoice email is queued, worker processes it, send_invoice_email is called."""
        executor = _BoundedInvoiceEmailExecutor.get_instance()

        with mock.patch.object(InvoiceEmailService, "send_invoice_email", return_value=(True, "Success")) as mock_send:
            queued = InvoiceEmailService.send_invoice_email_async(self.invoice.id)
            self.assertTrue(queued)

            executor._queue.join()

            mock_send.assert_called_once()
            args, kwargs = mock_send.call_args
            self.assertEqual(args[0].id, self.invoice.id)
            self.assertEqual(kwargs.get("trigger"), EmailTrigger.AUTOMATIC)

    def test_02_concurrency_limit_max_2_concurrent_workers(self):
        """Test 2: Submitting 10 jobs never exceeds MAX_WORKERS=2 concurrent executions."""
        executor = _BoundedInvoiceEmailExecutor.get_instance()
        active_count = 0
        max_active_count = 0
        count_lock = threading.Lock()

        def mock_slow_send_email(invoice, trigger=EmailTrigger.AUTOMATIC):
            nonlocal active_count, max_active_count
            with count_lock:
                active_count += 1
                if active_count > max_active_count:
                    max_active_count = active_count
            time.sleep(0.05)
            with count_lock:
                active_count -= 1
            return True, "Success"

        invoices = [
            Invoice.objects.create(
                organization=self.org,
                customer=self.customer,
                invoice_date=timezone.now().date(),
                place_of_supply="27",
                subtotal=10,
                grand_total=10,
                status=InvoiceStatus.DRAFT
            )
            for _ in range(10)
        ]

        with mock.patch.object(InvoiceEmailService, "send_invoice_email", side_effect=mock_slow_send_email):
            for inv in invoices:
                executor.submit(inv.id)

            executor._queue.join()

        self.assertLessEqual(max_active_count, _BoundedInvoiceEmailExecutor.MAX_WORKERS)
        self.assertEqual(max_active_count, 2)

    def test_03_burst_handling_50_jobs(self):
        """Test 3: Burst of 50 jobs processes safely without thread multiplication."""
        executor = _BoundedInvoiceEmailExecutor.get_instance()

        invoices = [
            Invoice.objects.create(
                organization=self.org,
                customer=self.customer,
                invoice_date=timezone.now().date(),
                place_of_supply="27",
                subtotal=10,
                grand_total=10,
                status=InvoiceStatus.DRAFT
            )
            for _ in range(50)
        ]

        with mock.patch.object(InvoiceEmailService, "send_invoice_email", return_value=(True, "Success")) as mock_send:
            for inv in invoices:
                queued = InvoiceEmailService.send_invoice_email_async(inv.id)
                self.assertTrue(queued)

            executor._queue.join()
            self.assertEqual(mock_send.call_count, 50)
            self.assertLessEqual(len(executor._workers), _BoundedInvoiceEmailExecutor.MAX_WORKERS)

    def test_04_queue_overflow_rejected_gracefully(self):
        """Test 4: Submitting more than MAX_QUEUE_SIZE (100) items rejects overflow gracefully."""
        executor = _BoundedInvoiceEmailExecutor.get_instance()
        executor._start_workers_if_needed()

        block_event = threading.Event()
        dummy_invoice = mock.MagicMock(id=1, organization=self.org)

        def blocking_get(*args, **kwargs):
            block_event.wait()
            return dummy_invoice

        with mock.patch("apps.billing.models.Invoice.objects.select_related") as mock_select, \
             mock.patch.object(InvoiceEmailService, "send_invoice_email", return_value=(True, "Success")):
            mock_select.return_value.get.side_effect = blocking_get

            # Fill 2 worker slots + 100 queue slots = 102 items
            for i in range(102):
                res = executor.submit(invoice_id=1000 + i)
                self.assertTrue(res, f"Item {i} should be accepted")

            # 103rd item must be rejected because queue is full (100 items waiting)
            overflow_result = executor.submit(invoice_id=9999)
            self.assertFalse(overflow_result)

            # Unblock workers so queue can drain
            block_event.set()
            executor._queue.join()

    def test_05_duplicate_protection(self):
        """Test 5: Submitting the same invoice ID multiple times while pending ignores duplicates."""
        executor = _BoundedInvoiceEmailExecutor.get_instance()
        block_event = threading.Event()

        def blocking_send(invoice, trigger=EmailTrigger.AUTOMATIC):
            block_event.wait()
            return True, "Success"

        with mock.patch.object(InvoiceEmailService, "send_invoice_email", side_effect=blocking_send):
            first_submit = executor.submit(self.invoice.id)
            self.assertTrue(first_submit)

            second_submit = executor.submit(self.invoice.id)
            self.assertFalse(second_submit)

            block_event.set()
            executor._queue.join()

    def test_06_pending_cleanup_after_success(self):
        """Test 6: Invoice ID is removed from pending_ids after successful execution."""
        executor = _BoundedInvoiceEmailExecutor.get_instance()

        with mock.patch.object(InvoiceEmailService, "send_invoice_email", return_value=(True, "Success")):
            executor.submit(self.invoice.id)
            executor._queue.join()

        with executor._lock:
            self.assertNotIn(self.invoice.id, executor._pending_ids)

    def test_07_pending_cleanup_after_failure(self):
        """Test 7: Invoice ID is removed from pending_ids after execution failure / exception."""
        executor = _BoundedInvoiceEmailExecutor.get_instance()

        with mock.patch.object(InvoiceEmailService, "send_invoice_email", side_effect=RuntimeError("PDF Failed")):
            executor.submit(self.invoice.id)
            executor._queue.join()

        with executor._lock:
            self.assertNotIn(self.invoice.id, executor._pending_ids)

    def test_08_failure_isolation(self):
        """Test 8: A failed job does not crash the worker or block subsequent jobs."""
        executor = _BoundedInvoiceEmailExecutor.get_instance()

        invoice2 = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=timezone.now().date(),
            place_of_supply="27",
            subtotal=10,
            grand_total=10,
            status=InvoiceStatus.DRAFT
        )

        calls = []

        def side_effect_send(invoice, trigger=EmailTrigger.AUTOMATIC):
            calls.append(invoice.id)
            if invoice.id == self.invoice.id:
                raise RuntimeError("Simulated failure for first invoice")
            return True, "Success"

        with mock.patch.object(InvoiceEmailService, "send_invoice_email", side_effect=side_effect_send):
            executor.submit(self.invoice.id)
            executor.submit(invoice2.id)

            executor._queue.join()

        self.assertIn(self.invoice.id, calls)
        self.assertIn(invoice2.id, calls)

    def test_09_transaction_rollback_prevents_email_job(self):
        """Test 9: Rolling back invoice issue transaction prevents on_commit email enqueueing."""
        inv = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=timezone.now().date(),
            place_of_supply="27",
            subtotal=10,
            grand_total=10,
            status=InvoiceStatus.DRAFT
        )

        with mock.patch.object(InvoiceEmailService, "send_invoice_email_async") as mock_async:
            try:
                with transaction.atomic():
                    prepare_invoice_snapshots(inv)
                    issue_invoice(inv)
                    raise RuntimeError("Force Rollback")
            except RuntimeError:
                pass

            mock_async.assert_not_called()

    def test_10_existing_invoice_issuance_behavior_unchanged(self):
        """Test 10: Invoice issuance lifecycle remains fully working and updates status."""
        self.assertEqual(self.invoice.status, InvoiceStatus.DRAFT)

        with mock.patch.object(InvoiceEmailService, "send_invoice_email_async") as mock_async:
            prepare_invoice_snapshots(self.invoice)
            issued = issue_invoice(self.invoice)
            self.assertEqual(issued.status, InvoiceStatus.ISSUED)
            self.assertTrue(issued.invoice_number.startswith("INV-"))
