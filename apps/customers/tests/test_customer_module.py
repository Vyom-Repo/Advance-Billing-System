"""
apps/customers/tests/test_customer_module.py — Customer V1 Unit & Integration Tests
"""
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.organization.models import Organization
from apps.customers.models import Customer, CustomerType, GSTStatus
from apps.customers.forms import CustomerForm

User = get_user_model()


class CustomerModuleTests(TestCase):
    def setUp(self):
        # Create Organization 1 and Owner 1
        self.user1 = User.objects.create_user(
            username="owner1",
            email="owner1@acme.com",
            password="Password123!",
            first_name="Owner",
            last_name="One"
        )
        self.org1 = Organization.objects.create(
            owner=self.user1,
            business_name="Acme Corp",
            business_email="contact@acme.com",
            address_line_1="123 Tech Park",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
            country="India"
        )

        # Create Organization 2 and Owner 2
        self.user2 = User.objects.create_user(
            username="owner2",
            email="owner2@beta.com",
            password="Password123!",
            first_name="Owner",
            last_name="Two"
        )
        self.org2 = Organization.objects.create(
            owner=self.user2,
            business_name="Beta Solutions",
            business_email="contact@beta.com",
            address_line_1="456 Innovation Way",
            city="Bengaluru",
            state="Karnataka",
            pincode="560001",
            country="India"
        )

        self.client1 = Client()
        self.client1.force_login(self.user1)

        self.client2 = Client()
        self.client2.force_login(self.user2)

        # Valid checksum GSTIN for Gujarat (24)
        self.valid_gstin_gujarat = "24AAAAC1201Q1ZS"

    def test_create_business_gst_registered_customer(self):
        """Scenario A: Create Business + GST Registered customer."""
        form_data = {
            "customer_type": CustomerType.BUSINESS,
            "gst_status": GSTStatus.REGISTERED,
            "name": "Reliance Industries Limited",
            "gstin": self.valid_gstin_gujarat,
            "billing_address_line_1": "Maker Chambers IV, Nariman Point",
            "billing_address_line_2": "Floor 3",
            "billing_city": "Mumbai",
            "state_select": "24",
            "billing_state": "Gujarat",
            "billing_state_code": "24",
            "billing_pin_code": "400021",
            "billing_country": "India",
        }
        form = CustomerForm(data=form_data, organization=self.org1)
        self.assertTrue(form.is_valid(), form.errors)
        
        customer = form.save(commit=False)
        customer.organization = self.org1
        customer.save()

        self.assertEqual(customer.name, "Reliance Industries Limited")
        self.assertEqual(customer.gstin, self.valid_gstin_gujarat)
        self.assertEqual(customer.billing_state_code, "24")
        self.assertEqual(customer.billing_state, "Gujarat")
        self.assertTrue(customer.is_registered)

    def test_create_business_gst_unregistered_customer(self):
        """Scenario B: Create Business + GST Unregistered customer."""
        form_data = {
            "customer_type": CustomerType.BUSINESS,
            "gst_status": GSTStatus.UNREGISTERED,
            "name": "Local General Store",
            "gstin": "24AAAAC1201Q1ZS",  # Should be cleared by form clean
            "billing_address_line_1": "Shop 12, Main Market",
            "billing_city": "Surat",
            "state_select": "24",
            "billing_state": "Gujarat",
            "billing_state_code": "24",
            "billing_pin_code": "395003",
            "billing_country": "India",
        }
        form = CustomerForm(data=form_data, organization=self.org1)
        self.assertTrue(form.is_valid(), form.errors)

        customer = form.save(commit=False)
        customer.organization = self.org1
        customer.save()

        self.assertEqual(customer.gstin, "")
        self.assertEqual(customer.gst_status, GSTStatus.UNREGISTERED)

    def test_create_individual_gst_registered_customer(self):
        """Scenario C: Create Individual + GST Registered customer."""
        form_data = {
            "customer_type": CustomerType.INDIVIDUAL,
            "gst_status": GSTStatus.REGISTERED,
            "name": "Dr. Rajesh Sharma",
            "gstin": self.valid_gstin_gujarat,
            "billing_address_line_1": "Flat 402, Green Avenue",
            "billing_city": "Ahmedabad",
            "state_select": "24",
            "billing_state": "Gujarat",
            "billing_state_code": "24",
            "billing_pin_code": "380015",
            "billing_country": "India",
        }
        form = CustomerForm(data=form_data, organization=self.org1)
        self.assertTrue(form.is_valid(), form.errors)

    def test_create_individual_gst_unregistered_customer(self):
        """Scenario D: Create Individual + GST Unregistered customer."""
        form_data = {
            "customer_type": CustomerType.INDIVIDUAL,
            "gst_status": GSTStatus.UNREGISTERED,
            "name": "Priya Patel",
            "billing_address_line_1": "15 Lotus Colony",
            "billing_city": "Vadodara",
            "state_select": "24",
            "billing_state": "Gujarat",
            "billing_state_code": "24",
            "billing_pin_code": "390001",
            "billing_country": "India",
        }
        form = CustomerForm(data=form_data, organization=self.org1)
        self.assertTrue(form.is_valid(), form.errors)

    def test_gstin_validation_invalid_length(self):
        """GSTIN shorter than 15 chars fails validation."""
        form_data = {
            "customer_type": CustomerType.BUSINESS,
            "gst_status": GSTStatus.REGISTERED,
            "name": "Short GSTIN Corp",
            "gstin": "24AAAAC1201Q1",  # 13 chars
            "billing_address_line_1": "123 High St",
            "billing_city": "Rajkot",
            "state_select": "24",
            "billing_state": "Gujarat",
            "billing_state_code": "24",
            "billing_pin_code": "360001",
            "billing_country": "India",
        }
        form = CustomerForm(data=form_data, organization=self.org1)
        self.assertFalse(form.is_valid())
        self.assertIn("gstin", form.errors)

    def test_pin_code_validation(self):
        """PIN code must be 6 numeric digits for India."""
        form_data = {
            "customer_type": CustomerType.BUSINESS,
            "gst_status": GSTStatus.UNREGISTERED,
            "name": "Bad Pin Corp",
            "billing_address_line_1": "123 High St",
            "billing_city": "Rajkot",
            "state_select": "24",
            "billing_state": "Gujarat",
            "billing_state_code": "24",
            "billing_pin_code": "36000",  # 5 digits
            "billing_country": "India",
        }
        form = CustomerForm(data=form_data, organization=self.org1)
        self.assertFalse(form.is_valid())
        self.assertIn("billing_pin_code", form.errors)

    def test_multi_tenant_isolation(self):
        """Organization 2 cannot see or edit Organization 1's customers."""
        cust1 = Customer.objects.create(
            organization=self.org1,
            customer_type=CustomerType.BUSINESS,
            gst_status=GSTStatus.UNREGISTERED,
            name="Org 1 Private Customer",
            billing_address_line_1="100 Private Rd",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_state_code="27",
            billing_pin_code="400001"
        )

        # Client 2 (Org 2) accesses Customer List
        resp = self.client2.get(reverse("customers:index"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Org 1 Private Customer", resp.content.decode())

        # Client 2 attempts to view Org 1's customer detail -> 404
        resp_detail = self.client2.get(reverse("customers:detail", kwargs={"uuid": cust1.uuid}))
        self.assertEqual(resp_detail.status_code, 404)

    def test_duplicate_registered_gstin_same_org(self):
        """Duplicate registered GSTIN in same organization fails validation."""
        Customer.objects.create(
            organization=self.org1,
            customer_type=CustomerType.BUSINESS,
            gst_status=GSTStatus.REGISTERED,
            name="First Registered Corp",
            gstin=self.valid_gstin_gujarat,
            billing_address_line_1="100 First St",
            billing_city="Ahmedabad",
            billing_state="Gujarat",
            billing_state_code="24",
            billing_pin_code="380001"
        )

        form_data = {
            "customer_type": CustomerType.BUSINESS,
            "gst_status": GSTStatus.REGISTERED,
            "name": "Second Registered Corp",
            "gstin": self.valid_gstin_gujarat,
            "billing_address_line_1": "200 Second St",
            "billing_city": "Surat",
            "state_select": "24",
            "billing_state": "Gujarat",
            "billing_state_code": "24",
            "billing_pin_code": "395001",
            "billing_country": "India",
        }
        form = CustomerForm(data=form_data, organization=self.org1)
        self.assertFalse(form.is_valid())
        self.assertIn("gstin", form.errors)

    def test_same_gstin_different_organizations_allowed(self):
        """Same GSTIN in different organizations is allowed."""
        Customer.objects.create(
            organization=self.org1,
            customer_type=CustomerType.BUSINESS,
            gst_status=GSTStatus.REGISTERED,
            name="Org 1 Customer",
            gstin=self.valid_gstin_gujarat,
            billing_address_line_1="100 First St",
            billing_city="Ahmedabad",
            billing_state="Gujarat",
            billing_state_code="24",
            billing_pin_code="380001"
        )

        form_data = {
            "customer_type": CustomerType.BUSINESS,
            "gst_status": GSTStatus.REGISTERED,
            "name": "Org 2 Customer",
            "gstin": self.valid_gstin_gujarat,
            "billing_address_line_1": "200 Second St",
            "billing_city": "Surat",
            "state_select": "24",
            "billing_state": "Gujarat",
            "billing_state_code": "24",
            "billing_pin_code": "395001",
            "billing_country": "India",
        }
        form = CustomerForm(data=form_data, organization=self.org2)
        self.assertTrue(form.is_valid(), form.errors)
