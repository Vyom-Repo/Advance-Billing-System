import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.db import transaction

from apps.billing.models import Invoice, InvoiceStatus
from apps.billing.services.lifecycle import issue_invoice, prepare_invoice_snapshots, prepare_invoice_snapshots, cancel_invoice, delete_invoice
from apps.organization.models import Organization
from apps.customers.models import Customer, GSTStatus
from apps.settings_app.models import InvoicePreference

User = get_user_model()


class InvoiceLifecycleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="test", email="test@example.com", password="password")
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Test Org",
            state_code="24"
        )
        self.pref = InvoicePreference.objects.create(
            user=self.user,
            invoice_prefix="INV",
            starting_number=1,
            include_financial_year=False
        )
        
        self.user2 = User.objects.create_user(username="test2", email="test2@example.com", password="password")
        self.org2 = Organization.objects.create(
            owner=self.user2,
            business_name="Test Org 2",
            state_code="24"
        )
        self.pref2 = InvoicePreference.objects.create(
            user=self.user2,
            invoice_prefix="INV",
            starting_number=1,
            include_financial_year=False
        )
        
        self.customer1 = Customer.objects.create(organization=self.org, name="Cust 1")
        self.customer2 = Customer.objects.create(organization=self.org2, name="Cust 2")

    def test_preview_numbering_formatting(self):
        # 1. Without financial year
        self.pref.include_financial_year = False
        self.assertEqual(self.pref.get_preview_number(), "INV-0001")
        
        # 2. With financial year
        self.pref.include_financial_year = True
        self.assertEqual(self.pref.get_preview_number(), "INV-2026-27-0001")
        
        # 3. No prefix
        self.pref.invoice_prefix = ""
        self.pref.include_financial_year = False
        self.assertEqual(self.pref.get_preview_number(), "0001")

    def test_new_invoice_is_draft(self):
        inv = Invoice.objects.create(
            organization=self.org,
            invoice_date=datetime.date.today(),
            place_of_supply="24",
            customer_name_snapshot="Test Customer",
            customer_state_code_snapshot="24"
        )
        self.assertEqual(inv.status, InvoiceStatus.DRAFT)
        self.assertEqual(inv.invoice_number, "")

    def test_issue_invoice_allocates_number(self):
        inv = Invoice.objects.create(
            organization=self.org,
            customer=self.customer1,
            invoice_date=datetime.date.today(),
            place_of_supply="24"
        )
        prepare_invoice_snapshots(inv)
        inv.save()
        for line in inv.lines.all(): line.save()
        lines = prepare_invoice_snapshots(inv)
        inv.save()
        for line in lines: line.save()
        issued_inv = issue_invoice(inv)
        self.assertEqual(issued_inv.status, InvoiceStatus.ISSUED)
        self.assertEqual(issued_inv.invoice_number, "INV-0001")
        
        self.pref.refresh_from_db()
        self.assertEqual(self.pref.starting_number, 2)

    def test_multiple_organizations_isolated_numbering(self):
        inv1 = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        inv2 = Invoice.objects.create(organization=self.org2, customer=self.customer2, invoice_date=datetime.date.today())
        
        prepare_invoice_snapshots(inv1)
        
        inv1.save()
        
        for line in inv1.lines.all(): line.save()
        
        issue_invoice(inv1)
        prepare_invoice_snapshots(inv2)
        inv2.save()
        for line in inv2.lines.all(): line.save()
        issue_invoice(inv2)
        
        self.assertEqual(inv1.invoice_number, "INV-0001")
        self.assertEqual(inv2.invoice_number, "INV-0001")

    def test_same_organization_increments_numbering(self):
        inv1 = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        inv2 = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        
        prepare_invoice_snapshots(inv1)
        
        inv1.save()
        
        for line in inv1.lines.all(): line.save()
        
        issue_invoice(inv1)
        prepare_invoice_snapshots(inv2)
        inv2.save()
        for line in inv2.lines.all(): line.save()
        issue_invoice(inv2)
        
        self.assertEqual(inv1.invoice_number, "INV-0001")
        self.assertEqual(inv2.invoice_number, "INV-0002")

    def test_duplicate_number_rejected_by_db(self):
        Invoice.objects.create(organization=self.org, invoice_date=datetime.date.today(), invoice_number="INV-0001")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.objects.create(organization=self.org, invoice_date=datetime.date.today(), invoice_number="INV-0001")

    def test_delete_draft_allowed(self):
        inv = Invoice.objects.create(organization=self.org, invoice_date=datetime.date.today())
        delete_invoice(inv)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_delete_issued_forbidden(self):
        inv = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        prepare_invoice_snapshots(inv)
        inv.save()
        for line in inv.lines.all(): line.save()
        issue_invoice(inv)
        
        with self.assertRaises(ValidationError):
            delete_invoice(inv)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_cancel_issued_allowed(self):
        inv = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        prepare_invoice_snapshots(inv)
        inv.save()
        for line in inv.lines.all(): line.save()
        issue_invoice(inv)
        orig_num = inv.invoice_number
        cancel_invoice(inv)
        self.assertEqual(inv.status, InvoiceStatus.CANCELLED)
        self.assertEqual(inv.invoice_number, f"{orig_num}-CANCELLED")

    def test_cancel_frees_number_and_allows_reissue(self):
        inv1 = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        prepare_invoice_snapshots(inv1)
        inv1.save()
        issue_invoice(inv1)
        orig_num = inv1.invoice_number

        # Cancel inv1
        cancel_invoice(inv1)
        self.assertEqual(inv1.status, InvoiceStatus.CANCELLED)
        self.assertEqual(inv1.invoice_number, f"{orig_num}-CANCELLED")

        # Create & issue inv2 - should reuse orig_num
        inv2 = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        prepare_invoice_snapshots(inv2)
        inv2.save()
        issue_invoice(inv2)
        self.assertEqual(inv2.invoice_number, orig_num)

    def test_repeated_cancel_and_reissue(self):
        # 1st attempt
        inv1 = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        prepare_invoice_snapshots(inv1)
        inv1.save()
        issue_invoice(inv1)
        num = inv1.invoice_number
        cancel_invoice(inv1)
        self.assertEqual(inv1.invoice_number, f"{num}-CANCELLED")

        # 2nd attempt
        inv2 = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        prepare_invoice_snapshots(inv2)
        inv2.save()
        issue_invoice(inv2)
        self.assertEqual(inv2.invoice_number, num)
        cancel_invoice(inv2)
        self.assertEqual(inv2.invoice_number, f"{num}-CANCELLED-{inv2.pk}")

        # 3rd attempt
        inv3 = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        prepare_invoice_snapshots(inv3)
        inv3.save()
        issue_invoice(inv3)
        self.assertEqual(inv3.invoice_number, num)

    def test_delete_cancelled_forbidden(self):
        inv = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        prepare_invoice_snapshots(inv)
        inv.save()
        for line in inv.lines.all(): line.save()
        issue_invoice(inv)
        cancel_invoice(inv)
        
        with self.assertRaises(ValidationError):
            delete_invoice(inv)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_issue_non_draft_fails(self):
        inv = Invoice.objects.create(organization=self.org, customer=self.customer1, invoice_date=datetime.date.today())
        prepare_invoice_snapshots(inv)
        inv.save()
        for line in inv.lines.all(): line.save()
        issue_invoice(inv)
        with self.assertRaises(ValidationError):
            prepare_invoice_snapshots(inv)
            inv.save()
            for line in inv.lines.all(): line.save()
            issue_invoice(inv)

    def test_cancel_non_issued_fails(self):
        inv = Invoice.objects.create(organization=self.org, invoice_date=datetime.date.today())
        with self.assertRaises(ValidationError):
            cancel_invoice(inv)

    def test_migration_recycles_legacy_cancelled_invoices(self):
        import importlib
        migration_module = importlib.import_module("apps.billing.migrations.0006_recycle_existing_cancelled_invoices")
        recycle_cancelled_invoices = migration_module.recycle_cancelled_invoices
        from unittest.mock import MagicMock

        # Create a legacy cancelled invoice without -CANCELLED suffix
        legacy_inv = Invoice.objects.create(
            organization=self.org,
            customer=self.customer1,
            invoice_number="INV-0099",
            status=InvoiceStatus.CANCELLED,
            invoice_date=datetime.date.today()
        )
        self.pref.starting_number = 100
        self.pref.save()

        # Run migration function
        mock_apps = MagicMock()
        mock_apps.get_model.side_effect = lambda app, model: {
            ('billing', 'Invoice'): Invoice,
            ('settings_app', 'InvoicePreference'): InvoicePreference,
            ('organization', 'Organization'): Organization,
        }[(app, model)]

        recycle_cancelled_invoices(mock_apps, None)

        legacy_inv.refresh_from_db()
        self.assertEqual(legacy_inv.invoice_number, "INV-0099-CANCELLED")

        self.pref.refresh_from_db()
        self.assertEqual(self.pref.starting_number, 1)
