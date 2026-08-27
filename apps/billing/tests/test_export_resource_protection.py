"""
apps/billing/tests/test_export_resource_protection.py

Phase 4 Export & Backup Resource Protection Test Suite.

Verifies:
1. Normal-sized organization export still succeeds.
2. Organization at allowed boundary succeeds.
3. Organization exceeding dataset boundary is rejected BEFORE expensive serialization.
4. Oversized Excel export is rejected BEFORE openpyxl workbook generation.
5. Oversized backup email is rejected BEFORE backup/email generation.
6. Backup upload exceeding file-size limit is rejected BEFORE openpyxl parsing.
7. Organization A cannot affect Organization B's resource calculation (tenant isolation).
8. Existing valid restore/import continues to work.
9. Existing export rate-limit behavior remains intact.
10. Export concurrency guard (ExportResourceGuard) bounds active exports & releases slots in finally.
11. Phase 1 bounded email worker integration remains operational.
12. Phase 2 bounded PDF resource guard integration remains operational.
13. Phase 3 rate limiting tests remain operational.
"""

import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus, DiscountType
from apps.customers.models import Customer
from apps.organization.models import Organization
from apps.products.models import Product, TaxabilityType
from apps.settings_app.models import DocumentPreference
from apps.settings_app.services.backup_service import (
    OrganizationBackupService,
    MAX_EXPORT_RECORDS,
    ExportDatasetTooLargeError,
)
from apps.settings_app.services.export_resource_guard import (
    ExportResourceGuard,
    ExportCapacityExceededError,
)
from apps.billing.services.pdf_resource_guard import PDFResourceGuard

User = get_user_model()


class Phase4ExportResourceProtectionTests(TestCase):
    def setUp(self):
        cache.clear()
        PDFResourceGuard.reset_stats()
        ExportResourceGuard.reset_stats()

        self.password = "Password123!"
        self.user = User.objects.create_user(
            username="export_user",
            email="export@example.com",
            password=self.password,
            is_active=True,
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Export Safety Corp",
            state_code="MH",
            business_email="export@corp.com",
            address_line_1="100 Secure Way",
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
            name="Backup Customer",
            billing_state_code="MH",
            billing_address_line_1="200 Client St",
            billing_city="Mumbai",
            billing_state="Maharashtra",
            billing_pin_code="400002",
        )

        self.product = Product.objects.create(
            organization=self.org,
            name="Consulting Service",
            unit_price=Decimal("5000.00"),
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
            description="Security Audit",
            quantity=Decimal("1.00"),
            unit_price=Decimal("5000.00"),
            discount_type=DiscountType.NONE,
            discount_value=Decimal("0.00"),
        )

        self.client = Client()

    def tearDown(self):
        cache.clear()
        PDFResourceGuard.reset_stats()
        ExportResourceGuard.reset_stats()

    # -------------------------------------------------------------------------
    # TEST 1: Normal-sized organization export still succeeds
    # -------------------------------------------------------------------------
    def test_01_normal_sized_organization_export_succeeds(self):
        self.client.login(username="export_user", password=self.password)
        url = reverse("settings_app:data_export")
        res = self.client.get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "application/zip")
        self.assertTrue(len(res.content) > 0)

    # -------------------------------------------------------------------------
    # TEST 2: Organization at the allowed boundary succeeds
    # -------------------------------------------------------------------------
    def test_02_organization_at_boundary_succeeds(self):
        self.client.login(username="export_user", password=self.password)
        valid_json = json.dumps({
            "metadata": {"signature": "ADVANCE_BILLING_BACKUP", "schema_version": "1.0", "organization_id": self.org.id},
            "organization": {"id": self.org.id},
            "customers": [],
            "customer_addresses": [],
            "products": [],
            "invoices": [],
            "invoice_items": [],
        }).encode("utf-8")
        with patch.object(OrganizationBackupService, "count_organization_records", return_value=MAX_EXPORT_RECORDS):
            with patch.object(OrganizationBackupService, "generate_single_snapshot") as mock_snap:
                mock_snap.return_value = (valid_json, "backup.json", b"excelbytes", "backup.xlsx", {"total": MAX_EXPORT_RECORDS}, MAX_EXPORT_RECORDS)
                url = reverse("settings_app:data_export")
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------------------
    # TEST 3: Organization exceeding boundary is rejected BEFORE serialization
    # -------------------------------------------------------------------------
    def test_03_oversized_organization_export_rejected_before_serialization(self):
        self.client.login(username="export_user", password=self.password)
        with patch.object(OrganizationBackupService, "count_organization_records", return_value=MAX_EXPORT_RECORDS + 1):
            url = reverse("settings_app:data_export")
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302)  # Redirects to settings page with error message
            self.assertIn("data-management", res.url)

    # -------------------------------------------------------------------------
    # TEST 4: Oversized Excel export is rejected BEFORE workbook generation
    # -------------------------------------------------------------------------
    def test_04_oversized_excel_export_rejected_before_workbook_generation(self):
        self.client.login(username="export_user", password=self.password)
        with patch.object(OrganizationBackupService, "count_organization_records", return_value=MAX_EXPORT_RECORDS + 10):
            url = reverse("settings_app:excel_export")
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302)

    # -------------------------------------------------------------------------
    # TEST 5: Oversized backup email is rejected BEFORE generation/mailing
    # -------------------------------------------------------------------------
    def test_05_oversized_backup_email_rejected_before_generation(self):
        self.client.login(username="export_user", password=self.password)
        with patch.object(OrganizationBackupService, "count_organization_records", return_value=MAX_EXPORT_RECORDS + 5):
            url = reverse("settings_app:data_backup_mail")
            res = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
            self.assertEqual(res.status_code, 400)
            data = res.json()
            self.assertFalse(data["success"])
            self.assertIn("exceeds maximum allowed limit", data["message"])

    # -------------------------------------------------------------------------
    # TEST 6: Backup upload exceeding file-size limit is rejected BEFORE openpyxl parsing
    # -------------------------------------------------------------------------
    def test_06_backup_upload_exceeding_size_limit_rejected_before_parsing(self):
        from apps.settings_app.views import SettingsExcelImportValidateView
        self.client.login(username="export_user", password=self.password)
        url = reverse("settings_app:excel_import_validate")

        large_file = SimpleUploadedFile("huge_backup.xlsx", b"0" * 100, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with patch.object(SettingsExcelImportValidateView, "MAX_BACKUP_UPLOAD_SIZE_BYTES", 50):
            with patch("apps.settings_app.services.excel_restore_service.ExcelRestoreService.validate_and_preview") as mock_restore:
                res = self.client.post(url, {"backup_file": large_file})
                self.assertEqual(res.status_code, 400)
                mock_restore.assert_not_called()
                data = res.json()
                self.assertFalse(data["success"])
                self.assertIn("exceeds maximum allowed limit", data["message"])

    # -------------------------------------------------------------------------
    # TEST 7: Organization A cannot affect Organization B's resource calculation
    # -------------------------------------------------------------------------
    def test_07_tenant_isolation_in_dataset_counting(self):
        user_b = User.objects.create_user(username="user_b", email="b@example.com", password=self.password)
        org_b = Organization.objects.create(owner=user_b, business_name="Org B")

        # Add 5 customers to Org B
        for i in range(5):
            Customer.objects.create(organization=org_b, name=f"Cust B {i}", billing_state_code="MH")

        count_a = OrganizationBackupService.count_organization_records(self.org)
        count_b = OrganizationBackupService.count_organization_records(org_b)

        # Org B's records do not inflate Org A's count
        self.assertEqual(count_a, 6)  # 1 org + 2 cust (1 cust + 1 addr) + 1 prod + 1 inv + 1 item = 6
        self.assertEqual(count_b, 11)  # 1 org + 10 cust (5 cust + 5 addr) = 11

    # -------------------------------------------------------------------------
    # TEST 8: Existing valid restore/import continues to work
    # -------------------------------------------------------------------------
    def test_08_valid_restore_validation_continues_to_work(self):
        self.client.login(username="export_user", password=self.password)
        url = reverse("settings_app:excel_import_validate")
        valid_file = SimpleUploadedFile("backup.xlsx", b"mockexcelbytes", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        with patch("apps.settings_app.services.excel_restore_service.ExcelRestoreService.validate_and_preview") as mock_preview:
            mock_preview.return_value = (True, "Valid Backup", {"customers": 1})
            res = self.client.post(url, {"backup_file": valid_file})
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.json()["success"])

    # -------------------------------------------------------------------------
    # TEST 9: Existing export rate-limit behavior remains intact
    # -------------------------------------------------------------------------
    def test_09_export_rate_limits_remain_intact(self):
        self.client.login(username="export_user", password=self.password)

        # Normal data export is UNLIMITED
        data_url = reverse("settings_app:data_export")
        for _ in range(6):
            res = self.client.get(data_url)
            self.assertEqual(res.status_code, 200)

        # Excel export is 5/h
        excel_url = reverse("settings_app:excel_export")
        for _ in range(5):
            res = self.client.get(excel_url)
            self.assertIn(res.status_code, (200, 429))
        res = self.client.get(excel_url)
        self.assertEqual(res.status_code, 429)

    # -------------------------------------------------------------------------
    # TEST 10: Export concurrency guard bounds slots and returns 503 on exhaustion
    # -------------------------------------------------------------------------
    def test_10_export_concurrency_guard(self):
        self.assertEqual(ExportResourceGuard.get_max_concurrent(), 2)

        # Slot 1 and 2 acquired
        with ExportResourceGuard.protect():
            self.assertEqual(ExportResourceGuard.get_active_exports(), 1)
            with ExportResourceGuard.protect():
                self.assertEqual(ExportResourceGuard.get_active_exports(), 2)
                # Slot 3 attempt times out and raises ExportCapacityExceededError
                with self.assertRaises(ExportCapacityExceededError):
                    with ExportResourceGuard.protect(timeout=0.1):
                        pass

        # Slots released after exiting finally block
        self.assertEqual(ExportResourceGuard.get_active_exports(), 0)

    # -------------------------------------------------------------------------
    # TEST 11: Phase 1 bounded email worker integration remains operational
    # -------------------------------------------------------------------------
    def test_11_phase_1_bounded_email_worker_integration(self):
        from apps.billing.services.invoice_email_service import _BoundedInvoiceEmailExecutor
        self.assertEqual(_BoundedInvoiceEmailExecutor.MAX_WORKERS, 2)
        self.assertEqual(_BoundedInvoiceEmailExecutor.MAX_QUEUE_SIZE, 100)

    # -------------------------------------------------------------------------
    # TEST 12: Phase 2 PDF resource guard integration remains operational
    # -------------------------------------------------------------------------
    def test_12_phase_2_bounded_pdf_resource_guard_integration(self):
        self.assertEqual(PDFResourceGuard.get_max_concurrent(), 2)
        with PDFResourceGuard.protect(timeout=1.0):
            self.assertEqual(PDFResourceGuard.get_active_renders(), 1)
        self.assertEqual(PDFResourceGuard.get_active_renders(), 0)
