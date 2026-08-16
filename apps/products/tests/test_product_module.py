"""
apps/products/tests/test_product_module.py — Product V1 Unit & Integration Tests

Covers:
  - Product type (Goods/Service): HSN/SAC conditional requirements
  - Taxability types (Taxable / Exempt / Nil-rated / Non-GST)
  - GST Rate validation (controlled list, decimal precision)
  - Cess (enabled / disabled)
  - Reverse Charge flag
  - Pricing (unit_price, inclusive/exclusive)
  - UQC (controlled values, reject free text)
  - Multi-tenancy isolation (Org A cannot access Org B's products)
  - Delete safety (product referenced by invoice_lines cannot be deleted)
  - Invoice snapshot integrity (edit product → old snapshot unchanged)
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse

from apps.organization.models import Organization
from apps.products.models import Product, ProductType, TaxabilityType, PriceBasis, CessType
from apps.products.forms import ProductForm
from apps.products.gst_config import GST_RATE_DEFAULT

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_org(username, business_name, email):
    user = User.objects.create_user(
        username=username,
        email=email,
        password="Password123!",
        first_name="Test",
        last_name="User",
    )
    org = Organization.objects.create(
        owner=user,
        business_name=business_name,
        business_email=email,
        address_line_1="123 Test Street",
        city="Mumbai",
        state="Maharashtra",
        pincode="400001",
        country="India",
    )
    return user, org


def _goods_data(**overrides):
    """Minimal valid Goods product form data."""
    data = {
        "name": "Steel Rod 10mm",
        "product_type": "goods",
        "hsn_code": "721410",
        "sac_code": "",
        "taxability_type": "taxable",
        "gst_rate": "18.00",
        "cess_applicable": "false",
        "cess_type": "",
        "cess_rate_or_amount": "",
        "reverse_charge_applicable": "false",
        "unit_price": "500.00",
        "price_basis": "exclusive",
        "uqc": "KGS",
    }
    data.update(overrides)
    return data


def _service_data(**overrides):
    """Minimal valid Service product form data."""
    data = {
        "name": "Web Development Services",
        "product_type": "service",
        "hsn_code": "",
        "sac_code": "998313",
        "taxability_type": "taxable",
        "gst_rate": "18.00",
        "cess_applicable": "false",
        "cess_type": "",
        "cess_rate_or_amount": "",
        "reverse_charge_applicable": "false",
        "unit_price": "5000.00",
        "price_basis": "exclusive",
        "uqc": "OTH",
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class ProductTypeTests(TestCase):
    def setUp(self):
        _, self.org = _make_org("owner1", "Acme Corp", "owner1@acme.com")

    def test_goods_requires_hsn(self):
        data = _goods_data(hsn_code="")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("hsn_code", form.errors)

    def test_goods_does_not_require_sac(self):
        data = _goods_data(sac_code="")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)

    def test_service_requires_sac(self):
        data = _service_data(sac_code="")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("sac_code", form.errors)

    def test_service_does_not_require_hsn(self):
        data = _service_data(hsn_code="")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)

    def test_goods_hsn_cleared_for_service(self):
        """When product_type=service, hsn_code must be cleared by clean()."""
        data = _service_data(hsn_code="721410")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["hsn_code"], "")

    def test_service_sac_cleared_for_goods(self):
        """When product_type=goods, sac_code must be cleared by clean()."""
        data = _goods_data(sac_code="998313")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["sac_code"], "")


class HSNSACValidationTests(TestCase):
    def setUp(self):
        _, self.org = _make_org("owner_hsn", "HSN Corp", "hsn@corp.com")

    def test_hsn_accepts_2_digit(self):
        form = ProductForm(data=_goods_data(hsn_code="72"), organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)

    def test_hsn_accepts_8_digit(self):
        form = ProductForm(data=_goods_data(hsn_code="72141099"), organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)

    def test_hsn_rejects_1_digit(self):
        form = ProductForm(data=_goods_data(hsn_code="7"), organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("hsn_code", form.errors)

    def test_hsn_rejects_9_digits(self):
        form = ProductForm(data=_goods_data(hsn_code="721410991"), organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("hsn_code", form.errors)

    def test_hsn_rejects_alpha(self):
        form = ProductForm(data=_goods_data(hsn_code="7214AB"), organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("hsn_code", form.errors)

    def test_sac_accepts_4_digit(self):
        form = ProductForm(data=_service_data(sac_code="9983"), organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)

    def test_sac_accepts_6_digit(self):
        form = ProductForm(data=_service_data(sac_code="998313"), organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)

    def test_sac_rejects_3_digit(self):
        form = ProductForm(data=_service_data(sac_code="998"), organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("sac_code", form.errors)

    def test_sac_rejects_7_digits(self):
        form = ProductForm(data=_service_data(sac_code="9983130"), organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("sac_code", form.errors)


class TaxabilityTests(TestCase):
    def setUp(self):
        _, self.org = _make_org("owner_tax", "Tax Corp", "tax@corp.com")

    def test_taxable_requires_gst_rate(self):
        data = _goods_data(taxability_type="taxable", gst_rate="")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("gst_rate", form.errors)

    def test_exempt_does_not_require_gst_rate(self):
        data = _goods_data(taxability_type="exempt", gst_rate="")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["gst_rate"], Decimal("0.00"))

    def test_nil_rated_does_not_require_gst_rate(self):
        data = _goods_data(taxability_type="nil_rated", gst_rate="")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["gst_rate"], Decimal("0.00"))

    def test_non_gst_does_not_require_gst_rate(self):
        data = _goods_data(taxability_type="non_gst", gst_rate="")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["gst_rate"], Decimal("0.00"))

    def test_all_four_taxability_types_valid(self):
        for taxability in ["taxable", "exempt", "nil_rated", "non_gst"]:
            gst = "18.00" if taxability == "taxable" else ""
            data = _goods_data(taxability_type=taxability, gst_rate=gst)
            form = ProductForm(data=data, organization=self.org)
            self.assertTrue(form.is_valid(), f"{taxability}: {form.errors}")


class GSTRateTests(TestCase):
    def setUp(self):
        _, self.org = _make_org("owner_rate", "Rate Corp", "rate@corp.com")

    def test_all_configured_rates_accepted(self):
        """Every rate in GST_RATE_CHOICES must be accepted by the form."""
        from apps.products.gst_config import GST_RATE_CHOICES
        for rate_val, _ in GST_RATE_CHOICES:
            data = _goods_data(gst_rate=rate_val)
            form = ProductForm(data=data, organization=self.org)
            self.assertTrue(form.is_valid(), f"Rate {rate_val} rejected: {form.errors}")

    def test_40_percent_rate_accepted(self):
        """40% was added to IRP Tax Rate Master in September 2025."""
        data = _goods_data(gst_rate="40.00")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)

    def test_arbitrary_rate_rejected(self):
        data = _goods_data(gst_rate="17.00")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("gst_rate", form.errors)

    def test_gst_rate_stored_as_decimal(self):
        data = _goods_data(gst_rate="18.00")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsInstance(form.cleaned_data["gst_rate"], Decimal)
        self.assertEqual(form.cleaned_data["gst_rate"], Decimal("18.00"))


class CessTests(TestCase):
    def setUp(self):
        _, self.org = _make_org("owner_cess", "Cess Corp", "cess@corp.com")

    def test_cess_disabled_by_default_saves_fine(self):
        data = _goods_data(cess_applicable="false")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["cess_applicable"])
        self.assertIsNone(form.cleaned_data["cess_rate_or_amount"])

    def test_cess_enabled_requires_type_and_amount(self):
        data = _goods_data(cess_applicable="true", cess_type="", cess_rate_or_amount="")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("cess_type", form.errors)
        self.assertIn("cess_rate_or_amount", form.errors)

    def test_cess_percentage_valid(self):
        data = _goods_data(cess_applicable="true", cess_type="percentage", cess_rate_or_amount="5.00")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["cess_applicable"])
        self.assertEqual(form.cleaned_data["cess_type"], "percentage")

    def test_cess_fixed_amount_valid(self):
        data = _goods_data(cess_applicable="true", cess_type="fixed_amount", cess_rate_or_amount="400.0000")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["cess_type"], "fixed_amount")

    def test_cess_fields_cleared_when_disabled(self):
        data = _goods_data(cess_applicable="false", cess_type="percentage", cess_rate_or_amount="5.00")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["cess_type"], "")
        self.assertIsNone(form.cleaned_data["cess_rate_or_amount"])


class ReverseChargeTests(TestCase):
    def setUp(self):
        _, self.org = _make_org("owner_rcm", "RCM Corp", "rcm@corp.com")

    def test_rcm_false_by_default(self):
        data = _goods_data(reverse_charge_applicable="false")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["reverse_charge_applicable"])

    def test_rcm_true_saves_correctly(self):
        data = _goods_data(reverse_charge_applicable="true")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["reverse_charge_applicable"])


class PricingTests(TestCase):
    def setUp(self):
        _, self.org = _make_org("owner_price", "Price Corp", "price@corp.com")

    def test_unit_price_required(self):
        data = _goods_data(unit_price="")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("unit_price", form.errors)

    def test_unit_price_must_be_positive(self):
        data = _goods_data(unit_price="0.00")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("unit_price", form.errors)

    def test_unit_price_stored_as_decimal(self):
        data = _goods_data(unit_price="999.99")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsInstance(form.cleaned_data["unit_price"], Decimal)

    def test_price_basis_exclusive(self):
        data = _goods_data(price_basis="exclusive")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price_basis"], "exclusive")

    def test_price_basis_inclusive(self):
        data = _goods_data(price_basis="inclusive")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["price_basis"], "inclusive")

    def test_price_basis_required(self):
        data = _goods_data(price_basis="")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("price_basis", form.errors)


class UQCTests(TestCase):
    def setUp(self):
        _, self.org = _make_org("owner_uqc", "UQC Corp", "uqc@corp.com")

    def test_valid_uqc_accepted(self):
        for uqc in ["NOS", "KGS", "LTR", "MTR", "PCS", "BOX", "OTH"]:
            data = _goods_data(uqc=uqc)
            form = ProductForm(data=data, organization=self.org)
            self.assertTrue(form.is_valid(), f"UQC {uqc}: {form.errors}")

    def test_arbitrary_free_text_rejected(self):
        data = _goods_data(uqc="EACH")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("uqc", form.errors)

    def test_goods_requires_uqc(self):
        data = _goods_data(uqc="")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("uqc", form.errors)

    def test_service_does_not_require_uqc(self):
        data = _service_data(uqc="")
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)


class MultiTenancyTests(TestCase):
    def setUp(self):
        self.user1, self.org1 = _make_org("mt_owner1", "Org One", "one@org.com")
        self.user2, self.org2 = _make_org("mt_owner2", "Org Two", "two@org.com")

        self.product1 = Product.objects.create(
            organization=self.org1,
            name="Org1 Exclusive Product",
            product_type=ProductType.GOODS,
            hsn_code="721410",
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            unit_price=Decimal("100.00"),
            price_basis=PriceBasis.EXCLUSIVE,
            uqc="KGS",
        )

        self.client1 = Client()
        self.client1.force_login(self.user1)
        self.client2 = Client()
        self.client2.force_login(self.user2)

    def test_org2_cannot_see_org1_products_in_list(self):
        resp = self.client2.get(reverse("products:index"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Org1 Exclusive Product", resp.content.decode())

    def test_org2_gets_404_on_org1_product_detail(self):
        url = reverse("products:detail", kwargs={"uuid": self.product1.uuid})
        resp = self.client2.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_org2_gets_404_on_org1_product_edit(self):
        url = reverse("products:edit", kwargs={"uuid": self.product1.uuid})
        resp = self.client2.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_org2_gets_404_on_org1_product_delete(self):
        url = reverse("products:delete", kwargs={"uuid": self.product1.uuid})
        resp = self.client2.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_org1_can_access_own_product(self):
        url = reverse("products:detail", kwargs={"uuid": self.product1.uuid})
        resp = self.client1.get(url)
        self.assertEqual(resp.status_code, 200)


class InvoiceSnapshotTests(TestCase):
    """
    Verify that as_invoice_snapshot() returns a stable dict and that
    editing the Product does not alter a previously captured snapshot.
    """

    def setUp(self):
        _, self.org = _make_org("snap_owner", "Snap Corp", "snap@corp.com")
        self.product = Product.objects.create(
            organization=self.org,
            name="Original Service Name",
            product_type=ProductType.SERVICE,
            sac_code="998313",
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            unit_price=Decimal("1000.00"),
            price_basis=PriceBasis.EXCLUSIVE,
            uqc="OTH",
        )

    def test_snapshot_contains_all_required_keys(self):
        snapshot = self.product.as_invoice_snapshot()
        required_keys = [
            "product_id", "product_uuid", "product_name", "product_type",
            "hsn_code", "sac_code", "classification_code",
            "taxability_type", "gst_rate",
            "cess_applicable", "cess_type", "cess_rate_or_amount",
            "reverse_charge_applicable",
            "unit_price", "price_basis", "uqc",
        ]
        for key in required_keys:
            self.assertIn(key, snapshot, f"Missing key: {key}")

    def test_snapshot_captures_correct_values(self):
        snapshot = self.product.as_invoice_snapshot()
        self.assertEqual(snapshot["product_name"],   "Original Service Name")
        self.assertEqual(snapshot["gst_rate"],       "18.00")
        self.assertEqual(snapshot["unit_price"],     "1000.00")
        self.assertEqual(snapshot["uqc"],            "OTH")
        self.assertEqual(snapshot["taxability_type"],"taxable")

    def test_editing_product_does_not_alter_old_snapshot(self):
        """
        Simulate the invoice pattern: snapshot is captured at invoice creation,
        then the product is edited — the snapshot must be unaffected.
        """
        # Capture snapshot (as invoice engine would do)
        snapshot_at_creation = self.product.as_invoice_snapshot()

        # Edit product
        self.product.gst_rate = Decimal("28.00")
        self.product.unit_price = Decimal("1500.00")
        self.product.name = "Renamed Service"
        self.product.save()

        # Snapshot from BEFORE the edit is unaffected
        self.assertEqual(snapshot_at_creation["gst_rate"],    "18.00")
        self.assertEqual(snapshot_at_creation["unit_price"],  "1000.00")
        self.assertEqual(snapshot_at_creation["product_name"],"Original Service Name")

    def test_snapshot_values_are_strings_not_floats(self):
        """Monetary values must be strings (from Decimal) to avoid float precision issues."""
        snapshot = self.product.as_invoice_snapshot()
        # These must be string representations, not float
        self.assertIsInstance(snapshot["gst_rate"],   str)
        self.assertIsInstance(snapshot["unit_price"], str)


class ProductCRUDTests(TestCase):
    """Basic form-level create/update integration tests."""

    def setUp(self):
        _, self.org = _make_org("crud_owner", "CRUD Corp", "crud@corp.com")

    def test_goods_product_creates_with_valid_data(self):
        data = _goods_data()
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save(commit=False)
        product.organization = self.org
        product.save()
        self.assertEqual(product.name, "Steel Rod 10mm")
        self.assertEqual(product.hsn_code, "721410")
        self.assertEqual(product.gst_rate, Decimal("18.00"))
        self.assertEqual(product.unit_price, Decimal("500.00"))
        self.assertEqual(product.uqc, "KGS")
        self.assertIsNotNone(product.uuid)

    def test_service_product_creates_with_valid_data(self):
        data = _service_data()
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save(commit=False)
        product.organization = self.org
        product.save()
        self.assertEqual(product.product_type, ProductType.SERVICE)
        self.assertEqual(product.sac_code, "998313")

    def test_product_name_required(self):
        data = _goods_data(name="")
        form = ProductForm(data=data, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_uuid_auto_generated_on_creation(self):
        data = _goods_data()
        form = ProductForm(data=data, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        product = form.save(commit=False)
        product.organization = self.org
        product.save()
        self.assertIsNotNone(product.uuid)

    def test_classification_code_property_goods(self):
        product = Product(product_type=ProductType.GOODS, hsn_code="721410", sac_code="")
        self.assertEqual(product.classification_code, "721410")

    def test_classification_code_property_service(self):
        product = Product(product_type=ProductType.SERVICE, hsn_code="", sac_code="998313")
        self.assertEqual(product.classification_code, "998313")
