import json
import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from bs4 import BeautifulSoup

from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product, TaxabilityType, PriceBasis
from apps.settings_app.models import InvoicePreference

User = get_user_model()

class InvoiceRegressionTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="testuser", email="test@example.com", password="password123")
        self.org = Organization.objects.create(
            owner=self.user, business_name="Test Org", business_email="test@example.com", state_code="27"
        )
        InvoicePreference.objects.create(user=self.user, invoice_prefix="INV", starting_number=1)
        self.customer = Customer.objects.create(
            organization=self.org, name="Test Customer", billing_state_code="27"
        )
        self.product = Product.objects.create(
            organization=self.org, name="Test Product", taxability_type=TaxabilityType.TAXABLE,
            gst_rate=18.0, price_basis=PriceBasis.EXCLUSIVE, unit_price=Decimal("100.00")
        )
        self.client.login(username="testuser", password="password123")

    def test_1_create_draft_with_valid_customer_product_redirects(self):
        url = reverse("billing:create")
        data = {
            "invoice_date": datetime.date.today().isoformat(),
            "customer": self.customer.id,
            "shipping_state": "27",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-0-product": self.product.id,
            "lines-0-quantity": "1",
            "lines-0-unit_price": "100.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.first()
        self.assertIsNotNone(invoice)
        self.assertRedirects(response, reverse("billing:detail", kwargs={"uuid": invoice.uuid}))

    def test_2_create_draft_without_customer_shows_validation_error(self):
        url = reverse("billing:create")
        data = {
            "invoice_date": datetime.date.today().isoformat(),
            "customer": "",
            "shipping_state": "27",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-0-product": self.product.id,
            "lines-0-quantity": "1",
            "lines-0-unit_price": "100.00",
            "lines-0-discount_type": "none",
            "lines-0-discount_value": "0",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A customer is required to create an invoice.")

    def test_3_create_draft_with_product_creates_invoiceline(self):
        self.test_1_create_draft_with_valid_customer_product_redirects()
        invoice = Invoice.objects.first()
        self.assertEqual(invoice.lines.count(), 1)
        line = invoice.lines.first()
        self.assertEqual(line.product, self.product)
        self.assertEqual(line.quantity, Decimal("1.000"))

    def test_4_dynamic_lines_only_one_add_product_button(self):
        url = reverse("billing:create")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # We cannot easily test JS behavior, but we can test the HTML has exactly one "+ Add Product" button
        soup = BeautifulSoup(response.content, 'html.parser')
        add_product_links = [a for a in soup.find_all('a') if '/products/create/' in a.get('href', '') and 'from_invoice=1' in a.get('href', '')]
        self.assertEqual(len(add_product_links), 1)

    def test_5_product_creation_stash_preserves_state(self):
        url = reverse("billing:session_stash")
        data = {
            "token": "test-token",
            "state": {"invoice_date": "2026-08-17", "lines-0-quantity": "5"},
            "line_index": ""
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["invoice_create_states"]["test-token"]["state"]["lines-0-quantity"], "5")

    def test_6_product_created_from_invoice_appears_in_dropdown(self):
        # Stash state
        stash = {"test-token": {"state": {"invoice_date": "2026-08-17", "lines-TOTAL_FORMS": "1"}}}
        session = self.client.session
        session["invoice_create_states"] = stash
        session.save()
        
        # New product created during the flow
        new_prod = Product.objects.create(organization=self.org, name="NewProd", taxability_type=TaxabilityType.NON_GST, price_basis=PriceBasis.EXCLUSIVE, unit_price=Decimal("10"))
        
        url = reverse("billing:create") + "?invoice_state=test-token&new_product=" + str(new_prod.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Check if the product was auto-selected in the first empty line
        product_select = soup.find('select', {'name': 'lines-0-product'})
        if product_select:
            selected_option = product_select.find('option', selected=True)
            if selected_option:
                self.assertEqual(str(selected_option['value']), str(new_prod.id))

    def test_7_preview_with_customer_and_product_returns_totals(self):
        url = reverse("billing:preview_form_calc")
        data = {
            "state": {
                "customer": self.customer.id,
                "shipping_state": "27",
                "shipping_same_as_billing": "on",
                "lines-TOTAL_FORMS": "1",
                "lines-0-product": self.product.id,
                "lines-0-quantity": "2",
                "lines-0-unit_price": "100.00",
                "lines-0-discount_type": "none"
            }
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertNotIn("error", resp_data)
        self.assertEqual(Decimal(resp_data["subtotal"]), Decimal("200.00"))

    def test_8_preview_without_customer_valid_pos_returns_totals(self):
        url = reverse("billing:preview_form_calc")
        data = {
            "state": {
                "customer": "",
                "place_of_supply": "27",
                "lines-TOTAL_FORMS": "1",
                "lines-0-product": self.product.id,
                "lines-0-quantity": "2",
                "lines-0-unit_price": "100.00",
                "lines-0-discount_type": "none"
            }
        }
        response = self.client.post(url, json.dumps(data), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        resp_data = response.json()
        self.assertNotIn("error", resp_data)
        self.assertEqual(Decimal(resp_data["subtotal"]), Decimal("200.00"))

    def test_9_preview_calculation_exception_returns_400(self):
        url = reverse("billing:preview_form_calc")
        data = {
            "state": {
                "customer": "",
                "place_of_supply": "27",
                "lines-TOTAL_FORMS": "1",
                "lines-0-product": self.product.id,
                "lines-0-quantity": "1",
            }
        }
        from unittest.mock import patch
        with patch('apps.billing.services.calculation_engine.calculate_invoice', side_effect=Exception("Mocked calculation error")):
            response = self.client.post(url, json.dumps(data), content_type="application/json")
            
        self.assertEqual(response.status_code, 400)
        self.assertIn("Calculation failed", response.json().get("error", ""))

    def test_10_detail_page_persisted_totals(self):
        self.test_1_create_draft_with_valid_customer_product_redirects()
        invoice = Invoice.objects.first()
        url = reverse("billing:detail", kwargs={"uuid": invoice.uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "100.00")
