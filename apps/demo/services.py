import uuid
import logging
from decimal import Decimal
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction

from apps.organization.models import Organization, PlanTier
from apps.customers.models import Customer
from apps.products.models import Product, ProductType, TaxabilityType, PriceBasis
from apps.billing.models import Invoice, InvoiceLine, InvoiceStatus, DiscountType
from apps.billing.services.calculation_engine import finalize_invoice

logger = logging.getLogger(__name__)
User = get_user_model()


class DemoService:
    @classmethod
    def create_isolated_demo_session(cls) -> tuple[User, Organization, str]:
        """
        Creates a brand-new, isolated temporary User and Organization for a unique demo session.
        Returns (user, org, session_id).
        """
        session_id = uuid.uuid4().hex[:12]
        username = f"demo_{session_id}"
        email = f"demo_{session_id}@demo.advancebilling.in"

        user = User.objects.create(
            username=username,
            email=email,
            first_name="Demo",
            last_name="Visitor",
            is_staff=False,
            is_superuser=False,
        )
        user.set_unusable_password()
        user.save()

        org = Organization.objects.create(
            owner=user,
            business_name="Advance Billing Demo",
            legal_business_name="Advance Billing Demo Pvt. Ltd.",
            is_gst_registered=True,
            gstin="29AAACA1234F1Z5",
            pan="AAACA1234F",
            state_code="29",
            business_email="demo@advancebilling.in",
            phone_number="+91 80 4567 8900",
            address_line_1="Suite 502, Tech Innovation Tower",
            address_line_2="Indiranagar 100ft Road",
            city="Bengaluru",
            state="Karnataka",
            pincode="560038",
            country="India",
            plan=PlanTier.FREE,
            terms_and_conditions="1. Payment is due within 15 days of invoice date.\n2. Please include invoice number in payment reference.",
            is_demo=True,
            demo_session_id=session_id,
        )

        cls.seed_demo_data(org, user)
        logger.info("Created new isolated demo session %s (Org ID: %s, User ID: %s)", session_id, org.id, user.id)
        return user, org, session_id

    @classmethod
    def seed_demo_data(cls, org: Organization, user: User):
        """
        Populates a demo organization with default sample customer, products, and invoices.
        """
        logger.info("Seeding sample data for demo org ID: %s", org.id)

        # 1. Demo Customer
        customer = Customer.objects.create(
            organization=org,
            name="Acme Technologies Pvt. Ltd.",
            customer_type="business",
            gst_status="registered",
            gstin="29ABCDE1234F1Z5",
            billing_address_line_1="42 Business Park",
            billing_address_line_2="Outer Ring Road",
            billing_city="Bengaluru",
            billing_state="Karnataka",
            billing_state_code="29",
            billing_pin_code="560001",
            billing_country="India",
        )

        # 2. Demo Products & Services
        p1 = Product.objects.create(
            organization=org,
            name="Website Development",
            product_type=ProductType.SERVICE,
            sac_code="998314",
            unit_price=Decimal("45000.00"),
            gst_rate=Decimal("18.0"),
            taxability_type=TaxabilityType.TAXABLE,
            price_basis=PriceBasis.EXCLUSIVE,
            uqc="OTH",
            description="Custom responsive web application development"
        )
        p2 = Product.objects.create(
            organization=org,
            name="UI/UX Design Package",
            product_type=ProductType.SERVICE,
            sac_code="998313",
            unit_price=Decimal("25000.00"),
            gst_rate=Decimal("18.0"),
            taxability_type=TaxabilityType.TAXABLE,
            price_basis=PriceBasis.EXCLUSIVE,
            uqc="OTH",
            description="Figma design system & interactive prototypes"
        )
        p3 = Product.objects.create(
            organization=org,
            name="Technical Consulting",
            product_type=ProductType.SERVICE,
            sac_code="998311",
            unit_price=Decimal("15000.00"),
            gst_rate=Decimal("18.0"),
            taxability_type=TaxabilityType.TAXABLE,
            price_basis=PriceBasis.EXCLUSIVE,
            uqc="OTH",
            description="Cloud architecture & security review"
        )
        p4 = Product.objects.create(
            organization=org,
            name="Annual Software Support",
            product_type=ProductType.SERVICE,
            sac_code="998319",
            unit_price=Decimal("12000.00"),
            gst_rate=Decimal("18.0"),
            taxability_type=TaxabilityType.TAXABLE,
            price_basis=PriceBasis.EXCLUSIVE,
            uqc="OTH",
            description="Priority SLA support & maintenance package"
        )

        # 3. Sample Invoice
        today = timezone.now().date()
        inv = Invoice.objects.create(
            organization=org,
            customer=customer,
            invoice_number="INV-DEMO-001",
            status=InvoiceStatus.DRAFT,
            invoice_date=today,
            due_date=today + timezone.timedelta(days=15),
            place_of_supply="29",
            notes="Thank you for partnering with Advance Billing!",
            terms=org.terms_and_conditions,
        )

        InvoiceLine.objects.create(
            invoice=inv,
            position=1,
            product=p1,
            product_name_snapshot=p1.name,
            description=p1.description,
            product_type_snapshot=p1.product_type,
            hsn_sac_snapshot=p1.sac_code,
            taxability_type_snapshot=p1.taxability_type,
            gst_rate_snapshot=p1.gst_rate,
            price_basis_snapshot=p1.price_basis,
            uqc_snapshot=p1.uqc,
            quantity=Decimal("1.00"),
            unit_price=p1.unit_price,
            discount_type=DiscountType.NONE,
        )

        InvoiceLine.objects.create(
            invoice=inv,
            position=2,
            product=p2,
            product_name_snapshot=p2.name,
            description=p2.description,
            product_type_snapshot=p2.product_type,
            hsn_sac_snapshot=p2.sac_code,
            taxability_type_snapshot=p2.taxability_type,
            gst_rate_snapshot=p2.gst_rate,
            price_basis_snapshot=p2.price_basis,
            uqc_snapshot=p2.uqc,
            quantity=Decimal("1.00"),
            unit_price=p2.unit_price,
            discount_type=DiscountType.NONE,
        )

        try:
            finalize_invoice(inv)
        except Exception as e:
            logger.error("Failed to finalize sample demo invoice: %s", str(e), exc_info=True)

    @classmethod
    def reset_demo_data(cls, org: Organization, user: User):
        """
        Resets modifications under the specified demo organization and re-seeds clean sample data.
        """
        if not org or not org.is_demo:
            logger.warning("Attempted reset on non-demo org %s", getattr(org, "id", None))
            return

        logger.info("Resetting demo data for demo org ID: %s", org.id)
        with transaction.atomic():
            InvoiceLine.objects.filter(invoice__organization=org).delete()
            Invoice.objects.filter(organization=org).delete()
            Product.objects.filter(organization=org).delete()
            Customer.objects.filter(organization=org).delete()
            cls.seed_demo_data(org, user)

    @classmethod
    def destroy_demo_session(cls, org: Organization, user: User) -> bool:
        """
        Safely and irreversibly purges a temporary demo organization and temporary demo user.
        STRICT GUARANTEE: Never deletes non-demo organizations (is_demo=False).
        """
        if not org or not getattr(org, "is_demo", False):
            logger.warning("Refusing deletion: Organization %s is not a marked demo organization.", getattr(org, "id", None))
            return False

        if not getattr(org, "demo_session_id", ""):
            logger.warning("Refusing deletion: Organization %s lacks demo_session_id.", org.id)
            return False

        from apps.common.models import Notification
        from apps.organization.models import UpgradeRequest
        from apps.settings_app.models import (
            OrganizationBackupSetting,
            OrganizationBackupLog,
            DataManagementAuditLog,
            UserBillPreference,
        )

        org_id = org.id
        user_id = user.id if user else None

        logger.info("Executing atomic purge for temporary demo org ID %s (session %s)...", org_id, org.demo_session_id)
        try:
            with transaction.atomic():
                InvoiceLine.objects.filter(invoice__organization=org).delete()
                Invoice.objects.filter(organization=org).delete()
                Customer.objects.filter(organization=org).delete()
                Product.objects.filter(organization=org).delete()
                Notification.objects.filter(organization=org).delete()

                if user:
                    UserBillPreference.objects.filter(user=user).delete()

                OrganizationBackupSetting.objects.filter(organization=org).delete()
                OrganizationBackupLog.objects.filter(organization=org).delete()
                DataManagementAuditLog.objects.filter(organization=org).delete()
                UpgradeRequest.objects.filter(organization=org).delete()

                org.delete()
                if user and getattr(user, "username", "").startswith("demo_"):
                    user.delete()

            logger.info("Successfully purged temporary demo org %s and user %s.", org_id, user_id)
            return True
        except Exception as e:
            logger.error("Failed to purge temporary demo org %s: %s", org_id, str(e), exc_info=True)
            return False

    @classmethod
    def cleanup_expired_demo_sessions(cls, max_age_hours: int = 2):
        """
        Conservative & idempotent abandoned demo session pruner.
        Purges temporary demo organizations older than `max_age_hours`.
        """
        cutoff = timezone.now() - timedelta(hours=max_age_hours)
        expired_orgs = Organization.objects.filter(
            is_demo=True,
            created_at__lt=cutoff
        ).exclude(demo_session_id="")

        count = 0
        for org in expired_orgs:
            owner = org.owner
            if cls.destroy_demo_session(org, owner):
                count += 1

        if count > 0:
            logger.info("Pruned %d expired demo sessions older than %d hours.", count, max_age_hours)
