"""
apps/settings_app/management/commands/preview_bill_template.py

Render any of the 8 PDF templates using sample data and save the output PDF
for visual QA — without running a web server.

Usage:
    python manage.py preview_bill_template compact_template
    python manage.py preview_bill_template vintage --output /tmp/vintage_test.pdf
    python manage.py preview_bill_template genz --user user@example.com
"""
import os

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Render a bill template to PDF with sample data for visual QA."

    def add_arguments(self, parser):
        parser.add_argument(
            "template_slug",
            type=str,
            help="Slug of the BillTemplate to preview (e.g. 'compact_template').",
        )
        parser.add_argument(
            "--output",
            type=str,
            default=None,
            help="Output PDF file path (default: /tmp/<slug>_preview.pdf).",
        )
        parser.add_argument(
            "--user",
            type=str,
            default=None,
            help="Email of a real user to load their org data (default: uses sample data).",
        )

    def handle(self, *args, **options):
        import weasyprint
        from django.template.loader import render_to_string
        from apps.invoices.services.invoice_preview_service import InvoicePreviewService
        from apps.invoices.services.bill_serializer import serialize_bill_for_render
        from apps.common.services.sample_data_service import SampleDataService
        from apps.common.services.layout_engine import PrintableFrameBuilder

        slug    = options["template_slug"]
        outpath = options["output"] or f"/tmp/{slug}_preview.pdf"
        tpl_path = f"pdf/{slug}.html"

        # Resolve user
        user = None
        if options["user"]:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(email=options["user"])
                self.stdout.write(f"Using real org data for user: {user.email}")
            except User.DoesNotExist:
                raise CommandError(f"No user found with email: {options['user']}")

        # Resolve config
        if user:
            config = InvoicePreviewService.resolve_render_config(slug, user)
        else:
            from apps.invoices.services.invoice_preview_service import _GLOBAL_DEFAULTS
            try:
                from apps.settings_app.models import BillTemplate
                bt = BillTemplate.objects.get(slug=slug)
                config = {**_GLOBAL_DEFAULTS, **bt.default_config}
                self.stdout.write(f"Loaded config from BillTemplate.{slug}")
            except Exception:
                config = dict(_GLOBAL_DEFAULTS)
                self.stdout.write("BillTemplate not seeded yet — using global defaults")

        # Build sample data
        company  = SampleDataService.sample_company()
        invoice  = SampleDataService.sample_invoice(user) if user else SampleDataService.sample_invoice_dict()
        customer = SampleDataService.sample_customer()
        items    = SampleDataService.sample_items()

        bill_data    = serialize_bill_for_render(invoice, customer, items, company, None)
        layout_frame = PrintableFrameBuilder.build_frame(None, config)

        try:
            pdf_bytes = InvoicePreviewService.render_bill_pdf(
                bill_data=bill_data,
                config=config,
                template_file_path=tpl_path,
                layout_frame=layout_frame,
            )
        except Exception as exc:
            raise CommandError(f"Render failed: {exc}") from exc

        # Write output
        os.makedirs(os.path.dirname(os.path.abspath(outpath)), exist_ok=True)
        with open(outpath, "wb") as f:
            f.write(pdf_bytes)

        self.stdout.write(self.style.SUCCESS(f"\nPDF saved → {outpath}"))
        self.stdout.write(f"Open it with: open {outpath}")
