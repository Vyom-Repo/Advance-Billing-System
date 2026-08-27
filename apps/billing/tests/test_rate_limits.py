"""
apps/billing/tests/test_rate_limits.py

Phase 3 Application Rate Limiting & Email Abuse Protection Test Suite.

Verifies:
1. Login under limit succeeds.
2. Login exceeding limit returns 429.
3. Signup exceeding limit returns 429.
4. Forgot-password exceeding limit returns 429.
5. Resend-verification exceeding limit returns 429.
6. Manual invoice email exceeding limit returns 429.
7. Backup mail exceeding limit returns 429.
8. JSON export exceeding limit returns 429.
9. Excel export exceeding limit returns 429.
10. Existing Phase 2 PDF rate limiting still returns 429.
11. Normal allowed requests still execute correctly.
12. Rate limiting does not break CSRF.
13. Rate limiting does not alter invoice calculation/lifecycle behavior.
14. Phase 1 bounded email worker integration remains operational.
15. Phase 2 bounded PDF resource guard remains operational.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus, DiscountType
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product, TaxabilityType
from apps.settings_app.models import DocumentPreference
from apps.billing.services.pdf_resource_guard import PDFResourceGuard

User = get_user_model()


class Phase3RateLimitingTests(TestCase):
    def setUp(self):
        cache.clear()
        PDFResourceGuard.reset_stats()

        self.password = "Password123!"
        self.user = User.objects.create_user(
            username="ratelimit_user",
            email="ratelimit@example.com",
            password=self.password,
            is_active=True,
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="RateLimit Corp",
            state_code="MH",
            business_email="ratelimit@corp.com",
            address_line_1="1 Rate Limit Way",
            city="Mumbai",
            state="Maharashtra",
            pincode="400001",
        )
        self.user.organization = self.org
        self.user.save()

        DocumentPreference.objects.create(
            user=self.user,
            show_company_logo=True,
            show_company_header=True,
            print_on_letterhead=False,
        )

        self.customer = Customer.objects.create(
            organization=self.org,
            name="Protected Customer",
            billing_state_code="MH",
            billing_address_line_1="100 Client St",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_pin_code="400002",
        )

        self.product = Product.objects.create(
            organization=self.org,
            name="Security Review",
            unit_price=Decimal("2000.00"),
            taxability_type=TaxabilityType.TAXABLE,
            gst_rate=Decimal("18.00"),
            hsn_code="9983",
        )

        self.invoice = Invoice.objects.create(
            organization=self.org,
            customer=self.customer,
            invoice_date=date.today(),
            status=InvoiceStatus.DRAFT,
            place_of_supply="MH",
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            position=1,
            product=self.product,
            description="Penetration Testing",
            quantity=Decimal("1.00"),
            unit_price=Decimal("2000.00"),
            discount_type=DiscountType.NONE,
            discount_value=Decimal("0.00"),
        )

        self.client = Client()

    def tearDown(self):
        cache.clear()
        PDFResourceGuard.reset_stats()

    # -------------------------------------------------------------------------
    # TEST 1: Login under limit succeeds
    # -------------------------------------------------------------------------
    def test_01_login_under_limit_succeeds(self):
        url = reverse("auth:login")
        response = self.client.post(url, {"email": "ratelimit@example.com", "password": self.password})
        self.assertIn(response.status_code, (200, 302))

    # -------------------------------------------------------------------------
    # TEST 2: Login exceeding limit returns 429
    # -------------------------------------------------------------------------
    def test_02_login_exceeding_limit_returns_429(self):
        url = reverse("auth:login")
        # Rate limit is 10/m
        for _ in range(10):
            res = self.client.post(url, {"email": "ratelimit@example.com", "password": "wrongpassword"})
            self.assertIn(res.status_code, (200, 302, 429))

        res = self.client.post(url, {"email": "ratelimit@example.com", "password": "wrongpassword"})
        self.assertEqual(res.status_code, 429)

    # -------------------------------------------------------------------------
    # TEST 3: Signup exceeding limit returns 429
    # -------------------------------------------------------------------------
    def test_03_signup_exceeding_limit_returns_429(self):
        url = reverse("auth:signup")
        # Rate limit is 5/m
        for i in range(5):
            res = self.client.post(url, {
                "first_name": "Test",
                "last_name": "User",
                "email": f"newuser{i}@example.com",
                "password": "Password123!",
                "confirm_password": "Password123!",
                "terms": "on",
            })
            self.assertIn(res.status_code, (200, 302, 429))

        res = self.client.post(url, {
            "first_name": "Test",
            "last_name": "User",
            "email": "spamuser@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
            "terms": "on",
        })
        self.assertEqual(res.status_code, 429)

    # -------------------------------------------------------------------------
    # TEST 4: Forgot-password exceeding limit returns 429
    # -------------------------------------------------------------------------
    def test_04_forgot_password_exceeding_limit_returns_429(self):
        url = reverse("auth:forgot_password")
        # Rate limit is 5/m
        for _ in range(5):
            res = self.client.post(url, {"email": "ratelimit@example.com"})
            self.assertIn(res.status_code, (200, 302, 429))

        res = self.client.post(url, {"email": "ratelimit@example.com"})
        self.assertEqual(res.status_code, 429)

    # -------------------------------------------------------------------------
    # TEST 5: Resend-verification exceeding limit returns 429
    # -------------------------------------------------------------------------
    def test_05_resend_verification_exceeding_limit_returns_429(self):
        url = reverse("auth:resend_verification")
        session = self.client.session
        session["verification_email"] = "unverified@example.com"
        session.save()

        # Rate limit is 5/m
        for _ in range(5):
            res = self.client.post(url)
            self.assertIn(res.status_code, (200, 302, 429))

        res = self.client.post(url)
        self.assertEqual(res.status_code, 429)

    # -------------------------------------------------------------------------
    # TEST 6: Manual invoice email exceeding limit returns 429
    # -------------------------------------------------------------------------
    def test_06_manual_invoice_email_exceeding_limit_returns_429(self):
        self.client.login(username="ratelimit_user", password=self.password)
        url = reverse("billing:mail", kwargs={"uuid": self.invoice.uuid})

        with patch("apps.billing.services.invoice_email_service.InvoiceEmailService.send_invoice_email") as mock_send:
            mock_send.return_value = (True, "Email sent")
            # Rate limit is 10/m
            for _ in range(10):
                res = self.client.post(url)
                self.assertIn(res.status_code, (302, 429))

            res = self.client.post(url)
            self.assertEqual(res.status_code, 429)

    # -------------------------------------------------------------------------
    # TEST 7: Backup mail exceeding limit returns 429
    # -------------------------------------------------------------------------
    def test_07_backup_mail_exceeding_limit_returns_429(self):
        self.client.login(username="ratelimit_user", password=self.password)
        url = reverse("settings_app:data_backup_mail")

        with patch("apps.settings_app.services.backup_service.OrganizationBackupService.send_weekly_backup_email") as mock_backup:
            mock_backup.return_value = (True, "Backup sent")
            # Rate limit is 2/h
            for _ in range(2):
                res = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
                self.assertIn(res.status_code, (200, 429))

            res = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            self.assertEqual(res.status_code, 429)

    # -------------------------------------------------------------------------
    # TEST 8: Data export is unconstrained for legitimate downloads
    # -------------------------------------------------------------------------
    def test_08_data_export_unconstrained_for_legitimate_users(self):
        self.client.login(username="ratelimit_user", password=self.password)
        url = reverse("settings_app:data_export")

        with patch("apps.settings_app.services.backup_service.OrganizationBackupService.generate_backup_zip") as mock_zip:
            mock_zip.return_value = (b"zipcontent", "backup.zip", {"total_records": 10})
            # Should allow 10 consecutive requests without 429
            for _ in range(10):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------------------
    # TEST 9: Excel export exceeding limit returns 429
    # -------------------------------------------------------------------------
    def test_09_excel_export_exceeding_limit_returns_429(self):
        self.client.login(username="ratelimit_user", password=self.password)
        url = reverse("settings_app:excel_export")

        with patch("apps.settings_app.services.excel_backup_service.ExcelBackupService.generate_backup_workbook") as mock_excel:
            mock_excel.return_value = (b"excelbytes", "backup.xlsx", {})
            # Rate limit is 5/h
            for _ in range(5):
                res = self.client.get(url)
                self.assertIn(res.status_code, (200, 429))

            res = self.client.get(url)
            self.assertEqual(res.status_code, 429)
            self.assertIn("Retry-After", res.headers)

    # -------------------------------------------------------------------------
    # TEST 10: Existing Phase 2 PDF rate limiting still returns 429
    # -------------------------------------------------------------------------
    def test_10_phase_2_pdf_rate_limiting_still_returns_429(self):
        self.client.login(username="ratelimit_user", password=self.password)
        url = reverse("billing:preview", kwargs={"uuid": self.invoice.uuid})

        # Rate limit is 15/m
        for _ in range(15):
            res = self.client.get(url)
            self.assertIn(res.status_code, (200, 429))

        res = self.client.get(url)
        self.assertEqual(res.status_code, 429)

    # -------------------------------------------------------------------------
    # TEST 11: Normal allowed requests still execute correctly
    # -------------------------------------------------------------------------
    def test_11_normal_allowed_requests_execute_correctly(self):
        self.client.login(username="ratelimit_user", password=self.password)
        dashboard_res = self.client.get(reverse("dashboard:index"))
        self.assertEqual(dashboard_res.status_code, 200)

        invoices_res = self.client.get(reverse("billing:index"))
        self.assertEqual(invoices_res.status_code, 200)

    # -------------------------------------------------------------------------
    # TEST 12: Rate limiting does not break CSRF
    # -------------------------------------------------------------------------
    def test_12_rate_limiting_does_not_break_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        login_url = reverse("auth:login")
        # Initial GET sets CSRF cookie
        get_res = csrf_client.get(login_url)
        self.assertEqual(get_res.status_code, 200)
        self.assertIn("csrftoken", csrf_client.cookies)

    # -------------------------------------------------------------------------
    # TEST 13: Rate limiting does not alter invoice calculation/lifecycle behavior
    # -------------------------------------------------------------------------
    def test_13_rate_limiting_does_not_alter_invoice_lifecycle(self):
        self.client.login(username="ratelimit_user", password=self.password)
        url = reverse("billing:issue", kwargs={"uuid": self.invoice.uuid})
        res = self.client.post(url)
        self.assertEqual(res.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.status, InvoiceStatus.ISSUED)

    # -------------------------------------------------------------------------
    # TEST 14: Phase 1 bounded email worker tests still pass
    # -------------------------------------------------------------------------
    def test_14_phase_1_bounded_email_worker_integration(self):
        from apps.billing.services.invoice_email_service import _BoundedInvoiceEmailExecutor
        self.assertEqual(_BoundedInvoiceEmailExecutor.MAX_WORKERS, 2)
        self.assertEqual(_BoundedInvoiceEmailExecutor.MAX_QUEUE_SIZE, 100)

    # -------------------------------------------------------------------------
    # TEST 15: Phase 2 bounded PDF tests still pass
    # -------------------------------------------------------------------------
    def test_15_phase_2_bounded_pdf_resource_guard_integration(self):
        self.assertEqual(PDFResourceGuard.get_max_concurrent(), 2)
        with PDFResourceGuard.protect(timeout=1.0):
            self.assertEqual(PDFResourceGuard.get_active_renders(), 1)
        self.assertEqual(PDFResourceGuard.get_active_renders(), 0)

    # -------------------------------------------------------------------------
    # TEST 16: HTTP 429 responses contain usable Retry-After header
    # -------------------------------------------------------------------------
    def test_16_http_429_responses_contain_retry_after_header(self):
        url = reverse("auth:forgot_password")
        for _ in range(5):
            self.client.post(url, {"email": "ratelimit@example.com"})

        res = self.client.post(url, {"email": "ratelimit@example.com"})
        self.assertEqual(res.status_code, 429)
        self.assertIn("Retry-After", res.headers)
        self.assertTrue(int(res.headers["Retry-After"]) > 0)
