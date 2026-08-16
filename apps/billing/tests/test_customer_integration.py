import datetime
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.billing.models import Invoice, InvoiceStatus
from apps.billing.services.lifecycle import issue_invoice, prepare_invoice_snapshots, prepare_invoice_snapshots, delete_invoice
from apps.billing.forms import InvoiceCustomerForm
from apps.organization.models import Organization
from apps.customers.models import Customer, GSTStatus
from apps.settings_app.models import InvoicePreference

User = get_user_model()


class CustomerIntegrationTests(TestCase):
    def setUp(self):
        # Org 1
        self.user = User.objects.create_user(username="test1", email="test@example.com", password="password")
        self.org = Organization.objects.create(owner=self.user, business_name="Test Org", state_code="24")
        self.pref = InvoicePreference.objects.create(user=self.user, invoice_prefix="INV", starting_number=1)
        
        self.customer1 = Customer.objects.create(
            organization=self.org,
            name="Alpha Corp",
            gst_status=GSTStatus.REGISTERED,
            gstin="24AAAAA0000A1Z5",
            billing_address_line_1="123 Alpha St",
            billing_city="Ahmedabad",
            billing_state="Gujarat",
            billing_state_code="24",
            billing_pin_code="380001"
        )
        self.customer2 = Customer.objects.create(
            organization=self.org,
            name="Beta Individual",
            gst_status=GSTStatus.UNREGISTERED,
            billing_address_line_1="456 Beta Ave",
            billing_city="Surat",
            billing_state="Gujarat",
            billing_state_code="24",
            billing_pin_code="395001"
        )

        # Org 2
        self.user2 = User.objects.create_user(username="test2", email="test2@example.com", password="password")
        self.org2 = Organization.objects.create(owner=self.user2, business_name="Test Org 2", state_code="24")
        self.pref2 = InvoicePreference.objects.create(user=self.user2, invoice_prefix="INV", starting_number=1)
        
        self.customer_org2 = Customer.objects.create(
            organization=self.org2,
            name="Omega Corp",
            gst_status=GSTStatus.REGISTERED,
            gstin="24BBBBB0000B1Z5",
            billing_address_line_1="789 Omega Blvd",
            billing_city="Rajkot",
            billing_state="Gujarat",
            billing_state_code="24",
            billing_pin_code="360001"
        )

    def test_invoice_customer_form_scoping(self):
        """Form must only show customers for the specified organization."""
        form = InvoiceCustomerForm(organization=self.org)
        queryset = form.fields['customer'].queryset
        
        self.assertIn(self.customer1, queryset)
        self.assertIn(self.customer2, queryset)
        self.assertNotIn(self.customer_org2, queryset)
        
    def test_invoice_customer_form_requires_organization(self):
        with self.assertRaises(ValueError):
            InvoiceCustomerForm()

    def test_draft_invoice_can_change_customer(self):
        """Customer can be changed on a Draft invoice."""
        inv = Invoice.objects.create(
            organization=self.org,
            customer=self.customer1,
            invoice_date=datetime.date.today()
        )
        self.assertEqual(inv.customer, self.customer1)
        
        # Change to another customer
        inv.customer = self.customer2
        inv.save()
        inv.refresh_from_db()
        self.assertEqual(inv.customer, self.customer2)

    def test_service_level_cross_tenant_rejection(self):
        """issue_invoice must reject cross-tenant customer assignments independently of the form."""
        inv = Invoice.objects.create(
            organization=self.org,
            customer=self.customer_org2, # Intentionally invalid
            invoice_date=datetime.date.today()
        )
        with self.assertRaises(ValidationError) as cm:
            prepare_invoice_snapshots(inv)
            inv.save()
            for line in inv.lines.all(): line.save()
            issue_invoice(inv)
            
        self.assertIn("Customer does not belong to the invoice's organization", str(cm.exception))

    def test_customer_snapshot_on_issue(self):
        """Issuing an invoice must correctly populate all snapshot fields from the Customer master."""
        inv = Invoice.objects.create(
            organization=self.org,
            customer=self.customer1,
            invoice_date=datetime.date.today()
        )
        
        prepare_invoice_snapshots(inv)
        
        inv.save()
        
        for line in inv.lines.all(): line.save()
        
        lines = prepare_invoice_snapshots(inv)
        inv.save()
        for line in lines: line.save()
        issued_inv = issue_invoice(inv)
        
        self.assertEqual(issued_inv.customer_name_snapshot, "Alpha Corp")
        self.assertEqual(issued_inv.customer_gstin_snapshot, "24AAAAA0000A1Z5")
        self.assertEqual(issued_inv.customer_billing_address_snapshot, "123 Alpha St, Ahmedabad, Gujarat (24), 380001, India")
        self.assertEqual(issued_inv.customer_state_code_snapshot, "24")

    def test_historical_integrity_after_customer_edit(self):
        """Modifying the Customer master post-issue must NOT alter the invoice snapshot."""
        inv = Invoice.objects.create(
            organization=self.org,
            customer=self.customer1,
            invoice_date=datetime.date.today()
        )
        prepare_invoice_snapshots(inv)
        inv.save()
        for line in inv.lines.all(): line.save()
        lines = prepare_invoice_snapshots(inv)
        inv.save()
        for line in lines: line.save()
        issued_inv = issue_invoice(inv)
        
        # Change Customer master
        self.customer1.name = "Alpha Corporation Ltd."
        self.customer1.billing_address_line_1 = "999 New Alpha St"
        self.customer1.save()
        
        # Refresh invoice
        issued_inv.refresh_from_db()
        
        # Assert snapshot remains intact
        self.assertEqual(issued_inv.customer_name_snapshot, "Alpha Corp")
        self.assertEqual(issued_inv.customer_billing_address_snapshot, "123 Alpha St, Ahmedabad, Gujarat (24), 380001, India")

    def test_customer_deletion_safety(self):
        """Deleting the customer master must preserve the invoice and its snapshot data (via SET_NULL)."""
        inv = Invoice.objects.create(
            organization=self.org,
            customer=self.customer1,
            invoice_date=datetime.date.today()
        )
        prepare_invoice_snapshots(inv)
        inv.save()
        for line in inv.lines.all(): line.save()
        lines = prepare_invoice_snapshots(inv)
        inv.save()
        for line in lines: line.save()
        issued_inv = issue_invoice(inv)
        
        invoice_uuid = issued_inv.uuid
        
        # Delete customer master
        self.customer1.delete()
        
        # Invoice still exists
        preserved_inv = Invoice.objects.get(uuid=invoice_uuid)
        self.assertIsNone(preserved_inv.customer)
        
        # Snapshot remains intact
        self.assertEqual(preserved_inv.customer_name_snapshot, "Alpha Corp")
        self.assertEqual(preserved_inv.customer_gstin_snapshot, "24AAAAA0000A1Z5")

    def test_unregistered_customer_snapshot(self):
        """Unregistered customers should have an empty GSTIN snapshot."""
        inv = Invoice.objects.create(
            organization=self.org,
            customer=self.customer2,
            invoice_date=datetime.date.today()
        )
        
        prepare_invoice_snapshots(inv)
        
        inv.save()
        
        for line in inv.lines.all(): line.save()
        
        lines = prepare_invoice_snapshots(inv)
        inv.save()
        for line in lines: line.save()
        issued_inv = issue_invoice(inv)
        
        self.assertEqual(issued_inv.customer_name_snapshot, "Beta Individual")
        self.assertEqual(issued_inv.customer_gstin_snapshot, "")
