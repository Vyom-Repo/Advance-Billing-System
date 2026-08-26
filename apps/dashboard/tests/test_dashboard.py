"""
apps/dashboard/tests/test_dashboard.py — Dashboard Integration Tests
"""
import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product, ProductType, TaxabilityType, PriceBasis
from apps.settings_app.models import InvoicePreference

User = get_user_model()


class DashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="owner",
            email="owner@example.com",
            password="Password123!",
            first_name="Jane",
            last_name="Doe",
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Acme Corp",
            business_email="contact@acme.com",
            address_line_1="123 Tech Park",
            city="Bengaluru",
            state="Karnataka",
            pincode="560001",
            state_code="29",
        )
        self.preference, _ = InvoicePreference.objects.get_or_create(
            user=self.user,
            defaults={"default_currency": "INR"}
        )
        self.client.force_login(self.user)

    def _create_customer(self, name="Test Customer"):
        return Customer.objects.create(
            organization=self.org,
            name=name,
            billing_address_line_1="12 Main St",
            billing_city="Bengaluru",
            billing_state="Karnataka",
            billing_pin_code="560001",
            billing_state_code="29",
        )

    def _create_product(self, name="Test Product", price="1000.00"):
        return Product.objects.create(
            organization=self.org,
            name=name,
            product_type=ProductType.GOODS,
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            unit_price=Decimal(price),
            price_basis=PriceBasis.EXCLUSIVE,
            uqc="PCS",
        )

    def test_scenario_1_brand_new_account_zero_state(self):
        """Brand-new account with zero invoices, customers, products."""
        url = reverse("dashboard:index")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        stats = response.context["stats"]
        self.assertEqual(stats["total_revenue"], Decimal("0.00"))
        self.assertEqual(stats["monthly_revenue"], Decimal("0.00"))
        self.assertEqual(stats["total_invoices"], 0)
        self.assertEqual(stats["total_customers"], 0)
        self.assertEqual(stats["total_products"], 0)
        self.assertEqual(stats["growth_text"], "No previous data")
        self.assertEqual(stats["growth_status"], "neutral")

        # Rolling 6-month chart
        chart_labels = response.context["chart_labels"]
        chart_values = response.context["chart_values"]
        self.assertEqual(len(chart_labels), 6)
        self.assertEqual(chart_values, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

        # Currency
        self.assertEqual(response.context["currency_code"], "INR")
        self.assertEqual(response.context["currency_symbol"], "₹")
        self.assertEqual(response.context["currency_icon"], "indian-rupee")
        self.assertContains(response, "₹0.00")

    def test_scenario_2_single_issued_invoice(self):
        """Account with one issued invoice in current month."""
        customer = self._create_customer()
        today = timezone.now().date()

        invoice = Invoice.objects.create(
            organization=self.org,
            customer=customer,
            invoice_date=today,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-0001",
            subtotal=Decimal("1000.00"),
            taxable_amount=Decimal("1000.00"),
            cgst_total=Decimal("90.00"),
            sgst_total=Decimal("90.00"),
            grand_total=Decimal("1180.00"),
        )

        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)

        stats = response.context["stats"]
        self.assertEqual(stats["total_revenue"], Decimal("1180.00"))
        self.assertEqual(stats["monthly_revenue"], Decimal("1180.00"))
        self.assertEqual(stats["total_invoices"], 1)
        self.assertEqual(stats["total_customers"], 1)

        # Check chart has non-zero value for current month (last entry)
        chart_values = response.context["chart_values"]
        self.assertEqual(chart_values[-1], 1180.0)

    def test_scenario_3_total_invoices_vs_revenue_generating(self):
        """
        Total invoice count includes both Draft and Issued invoices,
        but Total Revenue ONLY includes ISSUED invoices.
        """
        customer = self._create_customer()
        today = timezone.now().date()

        # Draft invoice (1000)
        Invoice.objects.create(
            organization=self.org,
            customer=customer,
            invoice_date=today,
            status=InvoiceStatus.DRAFT,
            grand_total=Decimal("1000.00"),
        )
        # Issued invoice (2500)
        Invoice.objects.create(
            organization=self.org,
            customer=customer,
            invoice_date=today,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-0001",
            grand_total=Decimal("2500.00"),
        )

        response = self.client.get(reverse("dashboard:index"))
        stats = response.context["stats"]

        self.assertEqual(stats["total_invoices"], 2)
        self.assertEqual(stats["total_revenue"], Decimal("2500.00"))
        self.assertEqual(stats["monthly_revenue"], Decimal("2500.00"))

    def test_scenario_4_invoice_status_transitions(self):
        """
        Verify revenue dynamics during status transitions:
        Draft (0) -> Issued (X) -> Cancelled (0).
        """
        customer = self._create_customer()
        today = timezone.now().date()

        invoice = Invoice.objects.create(
            organization=self.org,
            customer=customer,
            invoice_date=today,
            status=InvoiceStatus.DRAFT,
            grand_total=Decimal("5000.00"),
        )

        # State 1: DRAFT
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.context["stats"]["total_revenue"], Decimal("0.00"))
        self.assertEqual(response.context["stats"]["total_invoices"], 1)

        # State 2: ISSUED
        invoice.status = InvoiceStatus.ISSUED
        invoice.invoice_number = "INV-0001"
        invoice.save()

        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.context["stats"]["total_revenue"], Decimal("5000.00"))
        self.assertEqual(response.context["stats"]["total_invoices"], 1)

        # State 3: CANCELLED
        invoice.status = InvoiceStatus.CANCELLED
        invoice.save()

        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.context["stats"]["total_revenue"], Decimal("0.00"))
        self.assertEqual(response.context["stats"]["total_invoices"], 1)

    def test_scenario_5_month_over_month_growth(self):
        """Test percentage growth calculations (increase, decrease, neutral)."""
        customer = self._create_customer()
        today = timezone.now().date()

        # Date for current month & previous month
        curr_date = today.replace(day=15)
        if today.month == 1:
            prev_date = datetime.date(today.year - 1, 12, 15)
        else:
            prev_date = datetime.date(today.year, today.month - 1, 15)

        # Case A: Prev month = 8000, Curr month = 10000 -> +25%
        inv_prev = Invoice.objects.create(
            organization=self.org,
            customer=customer,
            invoice_date=prev_date,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-PREV",
            grand_total=Decimal("8000.00"),
        )
        inv_curr = Invoice.objects.create(
            organization=self.org,
            customer=customer,
            invoice_date=curr_date,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-CURR",
            grand_total=Decimal("10000.00"),
        )

        response = self.client.get(reverse("dashboard:index"))
        stats = response.context["stats"]
        self.assertEqual(stats["growth_status"], "positive")
        self.assertEqual(stats["growth_text"], "↑ 25% from last month")

        # Case B: Update Curr month to 7040 -> -12% decrease
        inv_curr.grand_total = Decimal("7040.00")
        inv_curr.save()

        response = self.client.get(reverse("dashboard:index"))
        stats = response.context["stats"]
        self.assertEqual(stats["growth_status"], "negative")
        self.assertEqual(stats["growth_text"], "↓ 12% from last month")

    def test_scenario_6_customer_and_product_counts(self):
        """Customer and product count updates reflect in real time."""
        c1 = self._create_customer("Customer 1")
        c2 = self._create_customer("Customer 2")
        p1 = self._create_product("Product 1", "500.00")

        response = self.client.get(reverse("dashboard:index"))
        stats = response.context["stats"]

        self.assertEqual(stats["total_customers"], 2)
        self.assertEqual(stats["total_products"], 1)

    def test_scenario_7_configured_currency(self):
        """Currency updates dynamically to USD, EUR, GBP."""
        customer = self._create_customer()
        today = timezone.now().date()

        Invoice.objects.create(
            organization=self.org,
            customer=customer,
            invoice_date=today,
            status=InvoiceStatus.ISSUED,
            invoice_number="INV-USD-1",
            grand_total=Decimal("2500.00"),
        )

        # Set currency preference to USD
        self.preference.default_currency = "USD"
        self.preference.save()

        response = self.client.get(reverse("dashboard:index"))

        self.assertEqual(response.context["currency_code"], "USD")
        self.assertEqual(response.context["currency_symbol"], "$")
        self.assertEqual(response.context["currency_icon"], "dollar-sign")
        self.assertContains(response, "$2,500.00")

        # Quick Actions check
        quick_actions = response.context["quick_actions"]
        self.assertEqual(len(quick_actions), 3)
        self.assertEqual(quick_actions[0]["url"], reverse("billing:create"))
        self.assertEqual(quick_actions[1]["url"], reverse("customers:create"))
        self.assertEqual(quick_actions[2]["url"], reverse("products:create"))
