"""
apps/invoices/services/invoice_preview_service.py

Provides the single rendering pipeline for all bill/invoice PDF templates.

Public API
----------
InvoicePreviewService.get_preview_context(user, custom_prefs, preview_mode)
    → Builds the full context dict (legacy-compatible; still used by views).

InvoicePreviewService.resolve_render_config(template_slug, user, request_overrides)
    → Merges BillTemplate.default_config → UserBillPreference.pref_overrides
      → request_overrides.  Validates keys. Returns clean config dict.

InvoicePreviewService.render_bill_pdf(bill_data, config, template_file_path, layout_frame)
    → Renders the Django template with the canonical context and returns
      the raw PDF bytes.  This is the ONE entry point for all 8 templates.
"""

from apps.common.services.organization_service import OrganizationService
from apps.common.services.sample_data_service import SampleDataService
from apps.common.services.layout_engine import PrintableFrameBuilder
from apps.settings_app.models import DocumentPreference
from apps.invoices.services.bill_serializer import serialize_bill_for_render, _file_url


# ---------------------------------------------------------------------------
# Shared defaults applied when a BillTemplate row doesn't exist yet
# (keeps the system functional before seed_bill_templates is run)
# ---------------------------------------------------------------------------
_GLOBAL_DEFAULTS: dict = {
    # Layout
    "paper_size":           "A4",
    "orientation":          "Portrait",
    "margins":              "Normal",
    "font_size":            "Medium",
    "table_density":        "Comfortable",
    # Visibility toggles
    "show_company_header":  True,
    "show_company_logo":    True,
    "show_company_footer":  True,
    "print_on_letterhead":  False,
    "show_qr_code":         True,
    "show_bank_details":    True,
    "show_gst_summary":     True,
    "show_hsn_sac":         True,
    "show_signature":       True,
    "show_terms":           True,
    "show_page_numbers":    True,
    "show_print_date":      True,
    "show_customer_name":   True,
    "show_customer_address":True,
    "show_customer_city":   True,
    "show_customer_state":  True,
    "show_customer_pincode":True,
    "show_customer_country":True,
    "show_customer_gstin":  True,
    "custom_footer_message":"Thank you for your business.",
    # Template-specific capability flags (False = not supported; overridden per template)
    "has_qr":               True,
    "has_signature":        True,
    "has_logo":             True,
    "has_bank_details":     True,
    "has_gst_summary":      True,
    "has_hsn_sac":          True,
    "has_tax_summary_table":False,
    "has_mrp_column":       False,
    "has_selling_price_column": False,
    "has_product_images":   False,
    "has_description_column": False,
    "has_receiver_signature": False,
    "has_dispatch_from":    False,
    "simplified_items":     False,
}


import logging
from django.template import loader
from django.template.exceptions import TemplateDoesNotExist, TemplateSyntaxError
import weasyprint

logger = logging.getLogger(__name__)

# Map legacy/alias template slugs to actual existing PDF template files
_TEMPLATE_SLUG_MAP = {
    "letterhead": "compact_template",
    "letterhead_invoice": "compact_template",
    "gst_classic": "compact_template",
    "flipkart_invoice": "compact_template",
    "retail_gst_compact": "compact_template",
    "evergreen": "professional_template",
    "compact": "compact_template",
    "professional": "professional_template",
    "landscape": "landscape_template",
    "modern": "modern_template",
    "mrp_discount": "mrp_discount_template",
    "service": "service_template",
    "simple": "simple_invoice",
    "simple_invoice": "simple_invoice",
    "ledger_classic": "compact_template",
    "minimal_mono": "compact_template",
    "bold_header": "compact_template",
    "elegant_serif": "compact_template",
    "tech_grid": "compact_template",
}


class InvoicePreviewService:

    # ------------------------------------------------------------------
    # resolve_template_path
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_template_path(template_file_or_slug: str) -> str:
        """
        Resolves a slug to a production template path.
        """
        normalized_slug = template_file_or_slug.replace("pdf/", "").replace(".html", "") if template_file_or_slug else "professional_template"
        mapped_slug = _TEMPLATE_SLUG_MAP.get(normalized_slug, normalized_slug)
        return f"pdf/{mapped_slug}.html"

    # ------------------------------------------------------------------
    # resolve_render_config
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_render_config(
        template_slug: str | None = None,
        user=None,
        request_overrides: dict | None = None,
    ) -> dict:
        """
        Build the final, validated config dict for a render.

        Resolution order (lowest → highest priority):
            1. _GLOBAL_DEFAULTS
            2. BillTemplate.default_config  (template-specific capability declaration)
            3. DocumentPreference fields    (user's global document prefs)
            4. UserBillPreference.pref_overrides  (per-template user overrides)
            5. request_overrides            (one-off per-request, never persisted)

        Template slug is resolved via deterministic 3-tier hierarchy:
            Tier 1: Explicitly supplied request_overrides['template_name'] or template_slug
            Tier 2: User's saved DocumentPreference.template_name from DB
            Tier 3: System default fallback ('professional_template')
        """
        from apps.settings_app.models import BillTemplate, UserBillPreference, DocumentPreference

        # Resolve effective slug via 3-tier hierarchy
        effective_slug = None
        if request_overrides and request_overrides.get("template_name"):
            effective_slug = str(request_overrides["template_name"]).strip()
        elif template_slug:
            effective_slug = str(template_slug).strip()

        if not effective_slug and user and getattr(user, "is_authenticated", True):
            try:
                saved_slug = DocumentPreference.objects.filter(user=user).values_list("template_name", flat=True).first()
                if saved_slug:
                    effective_slug = saved_slug
            except Exception:
                pass

        if not effective_slug:
            effective_slug = "professional_template"

        normalized_slug = effective_slug.replace("pdf/", "").replace(".html", "")
        mapped_slug = _TEMPLATE_SLUG_MAP.get(normalized_slug, normalized_slug)

        # --- Layer 1: global defaults ---
        config = dict(_GLOBAL_DEFAULTS)
        config["template_name"] = mapped_slug

        # --- Layer 2: BillTemplate.default_config ---
        try:
            bt = BillTemplate.objects.get(slug=mapped_slug)
            allowed_keys = bt.get_allowed_config_keys()
            config.update(bt.default_config)
            config["template_name"] = mapped_slug
        except BillTemplate.DoesNotExist:
            try:
                bt = BillTemplate.objects.get(slug=normalized_slug)
                allowed_keys = bt.get_allowed_config_keys()
                config.update(bt.default_config)
                config["template_name"] = mapped_slug
            except BillTemplate.DoesNotExist:
                bt = None
                allowed_keys = set(_GLOBAL_DEFAULTS.keys())
                config["template_name"] = mapped_slug

        # --- Layer 3: DocumentPreference (user's global prefs) ---
        try:
            doc_pref = DocumentPreference.objects.get(user=user)
            _merge_doc_prefs(config, doc_pref)
        except DocumentPreference.DoesNotExist:
            pass

        # --- Layer 4: UserBillPreference.pref_overrides ---
        if bt is not None:
            try:
                ubp = UserBillPreference.objects.get(user=user, template=bt)
                _merge_validated(config, ubp.pref_overrides, allowed_keys)
            except UserBillPreference.DoesNotExist:
                pass

        # --- Layer 5: request_overrides (one-off, not persisted) ---
        if request_overrides:
            _merge_validated(config, request_overrides, allowed_keys)

        return config

    # ------------------------------------------------------------------
    # render_invoice_to_pdf (Canonical ORM pipeline)
    # ------------------------------------------------------------------

    @classmethod
    def render_invoice_to_pdf(cls, invoice, user=None) -> bytes:
        """
        Canonical high-level entry point for rendering an Invoice ORM object to PDF bytes.
        Ensures exact 100% rendering parity between Portal PDF view/download and Email attachments.
        """
        from apps.billing.services.pdf_adapter import invoice_to_pdf_dicts
        from apps.invoices.services.bill_serializer import serialize_bill_for_render
        from apps.common.services.layout_engine import PrintableFrameBuilder

        org = getattr(invoice, "organization", None)
        if user is None and org:
            user = getattr(org, "owner", None)

        invoice_dict, customer_dict, items_list, company_dict = invoice_to_pdf_dicts(invoice)
        bill_data = serialize_bill_for_render(
            invoice=invoice_dict,
            customer=customer_dict,
            items=items_list,
            company=company_dict,
            org=org,
        )
        config = cls.resolve_render_config(user=user)
        layout_frame = PrintableFrameBuilder.build_frame(org, config)
        template_file_path = cls.resolve_template_path(config.get("template_name"))

        return cls.render_bill_pdf(
            bill_data=bill_data,
            config=config,
            template_file_path=template_file_path,
            layout_frame=layout_frame,
            org=org,
        )

    # ------------------------------------------------------------------
    # render_bill_pdf
    # ------------------------------------------------------------------

    @staticmethod
    def render_bill_pdf(
        bill_data: dict,
        config: dict,
        template_file_path: str,
        layout_frame: dict,
        org=None,
    ) -> bytes:
        """
        Single entry point for rendering any PDF template with automatic fallback.

        If rendering the primary template fails or produces invalid PDF bytes,
        it automatically falls back to rendering pdf/simple_invoice.html.

        Parameters
        ----------
        bill_data          : dict — output of serialize_bill_for_render()
                             (keys: bill, company, customer, items, gst_summary)
        config             : dict — output of resolve_render_config()
        template_file_path : str  — Django template path e.g. "pdf/genz.html"
        layout_frame       : dict — output of PrintableFrameBuilder.build_frame()
        org                : Organization instance or None

        Returns
        -------
        bytes — raw PDF binary
        """
        from django.template.loader import render_to_string
        from apps.billing.services.pdf_resource_guard import PDFResourceGuard, PDFCapacityExceededError

        context = {
            **bill_data,        # bill, company, customer, items, gst_summary
            "config":       config,
            "layout_frame": layout_frame,
            "org":          org,
            # Legacy keys kept for backward-compat
            "prefs":        config,
            "invoice":      bill_data.get("bill", {}),
            "customer":     bill_data.get("customer", {}),
            "items":        bill_data.get("items", []),
            "company":      bill_data.get("company", {}),
            # Watermark: True for FREE accounts, False for PAID.
            # Decision is purely server-side — org.plan read from DB.
            "show_watermark": (org is not None and getattr(org, "plan", "free") == "free"),
        }

        # Preserve user's selected template choice regardless of whether letterhead is enabled.
        primary_path = template_file_path

        with PDFResourceGuard.protect():
            try:
                html_string = render_to_string(primary_path, context)
                pdf_bytes = weasyprint.HTML(
                    string=html_string,
                    base_url="file://",
                ).write_pdf()

                if isinstance(pdf_bytes, bytes) and pdf_bytes.startswith(b"%PDF") and len(pdf_bytes) > 500:
                    return pdf_bytes
                else:
                    logger.warning(
                        "Primary template '%s' produced empty or invalid PDF bytes. Retrying with fallback.",
                        primary_path,
                    )
            except PDFCapacityExceededError:
                raise
            except Exception as e:
                logger.warning(
                    "Primary template '%s' rendering failed (%s). Automatically falling back.",
                    primary_path,
                    str(e),
                    exc_info=True,
                )

            # Fallback render hierarchy: simple_invoice.html if primary template rendering fails
            fallback_template = "pdf/simple_invoice.html"
            try:
                fallback_html = render_to_string(fallback_template, context)
                fallback_pdf = weasyprint.HTML(
                    string=fallback_html,
                    base_url="file://",
                ).write_pdf()
                return fallback_pdf
            except PDFCapacityExceededError:
                raise
            except Exception as fallback_err:
                logger.error(
                    "Fallback template pdf/simple_invoice.html failed to render: %s",
                    str(fallback_err),
                    exc_info=True,
                )

                # Emergency inline fallback (guarantees a valid PDF response)
                emergency_html = f"""
                <!DOCTYPE html>
                <html>
                <head><meta charset="utf-8"><title>Invoice Emergency PDF</title></head>
                <body style="font-family: sans-serif; padding: 30px;">
                    <h2>TAX INVOICE - {bill_data.get('bill', {}).get('number', 'INV-001')}</h2>
                    <p><strong>Company:</strong> {bill_data.get('company', {}).get('name', '')}</p>
                    <p><strong>Billed To:</strong> {bill_data.get('customer', {}).get('name', '')}</p>
                    <p><strong>Grand Total:</strong> {bill_data.get('bill', {}).get('grand_total', '0.00')}</p>
                </body>
                </html>
                """
                return weasyprint.HTML(string=emergency_html).write_pdf()


    # ------------------------------------------------------------------
    # get_preview_context  (legacy — kept for backward compatibility)
    # ------------------------------------------------------------------

    @staticmethod
    def get_preview_context(user, custom_prefs=None, preview_mode=None):
        """
        Merge organization data, invoice preferences, and sample/real data
        into a single rendering context.

        This method is the original entry point and is preserved for backward
        compatibility.  New code should use resolve_render_config() +
        render_bill_pdf() directly.

        The returned dict now includes the canonical ``bill`` key in addition
        to the legacy ``invoice`` key, so old templates that read ``{{ invoice.xxx }}``
        continue to work while new templates can read ``{{ bill.xxx }}``.
        """
        if preview_mode == "demo":
            company = SampleDataService.sample_company()
            org_obj = None
        else:
            org_data = OrganizationService.get_company_assets(user)
            if org_data:
                company = {
                    "name": org_data["business_name"],
                    "address": f"{org_data['address_line_1']} {org_data['address_line_2']}".strip(),
                    "city": org_data["city"],
                    "state": org_data["state"],
                    "gstin": org_data["gstin"],
                    "email": org_data["email"],
                    "phone": org_data["phone"],
                    "logo_url": _file_url(org_data.get("logo")),
                    "signature_url": _file_url(org_data.get("signature")),
                    "letterhead_url": _file_url(org_data.get("letterhead")),
                }
                if org_data["default_bank"]:
                    company["bank_name"] = org_data["default_bank"].bank_name
                    company["acc_no"] = org_data["default_bank"].account_number
                    company["ifsc"] = org_data["default_bank"].ifsc_code
                org_obj = org_data["organization"]
            else:
                company = SampleDataService.sample_company()
                org_obj = None

        template_slug = (custom_prefs or {}).get("template_name")
        config = InvoicePreviewService.resolve_render_config(
            template_slug=template_slug,
            user=user,
            request_overrides=custom_prefs,
        )

        frame = PrintableFrameBuilder.build_frame(org_obj, config)

        invoice  = SampleDataService.sample_invoice(user)
        customer = SampleDataService.sample_customer()
        items    = SampleDataService.sample_items()

        # Build canonical bill data (new key; old keys kept for compat)
        canonical = serialize_bill_for_render(invoice, customer, items, company, org_obj)

        context = {
            # --- Canonical keys (used by new templates) ---
            **canonical,        # bill, company, customer, items, gst_summary
            "config":       config,
            "layout_frame": frame,
            "org":          org_obj,
            # --- Legacy keys (used by old/partial templates) ---
            "invoice":      invoice,
            "prefs":        config,
            # Watermark: True for FREE accounts, False for PAID.
            "show_watermark": (org_obj is not None and getattr(org_obj, "plan", "free") == "free"),
        }
        return context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_doc_prefs(config: dict, doc_pref) -> None:
    """Pull relevant fields from DocumentPreference into config."""
    field_map = {
        "paper_size":            "paper_size",
        "orientation":           "orientation",
        "margins":               "margins",
        "font_size":             "font_size",
        "table_density":         "table_density",
        "show_company_logo":     "show_company_logo",
        "show_company_header":   "show_company_header",
        "show_company_footer":   "show_company_footer",
        "print_on_letterhead":   "print_on_letterhead",
        "show_qr_code":          "show_qr_code",
        "show_bank_details":     "show_bank_details",
        "show_gst_summary":      "show_gst_summary",
        "show_hsn_sac":          "show_hsn_sac",
        "show_signature":        "show_signature",
        "show_terms":            "show_terms",
        "show_page_numbers":     "show_page_numbers",
        "show_print_date":       "show_print_date",
        "show_customer_name":    "show_customer_name",
        "show_customer_address": "show_customer_address",
        "show_customer_city":    "show_customer_city",
        "show_customer_state":   "show_customer_state",
        "show_customer_pincode": "show_customer_pincode",
        "show_customer_country": "show_customer_country",
        "show_customer_gstin":   "show_customer_gstin",
        "custom_footer_message": "custom_footer_message",
    }
    for config_key, pref_attr in field_map.items():
        value = getattr(doc_pref, pref_attr, None)
        if value is not None:
            config[config_key] = value


def _merge_validated(config: dict, overrides: dict | None, allowed_keys: set) -> None:
    """
    Merge ``overrides`` into ``config``, only for keys in ``allowed_keys``.
    Invalid/unknown keys are silently dropped (never fail a render).
    """
    if not isinstance(overrides, dict):
        return

    for key, value in overrides.items():
        if key in allowed_keys:
            expected = config.get(key)
            expected_type = type(expected) if expected is not None else None

            # Coerce / validate booleans
            if expected_type is bool:
                if isinstance(value, str):
                    value = value.strip().lower() in ("true", "1", "yes", "on")
                elif isinstance(value, (int, float)):
                    value = bool(value)
                elif not isinstance(value, bool):
                    continue
            # Coerce / validate floats
            elif expected_type is float:
                if isinstance(value, str):
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        continue
                elif isinstance(value, (int, float)):
                    value = float(value)
                else:
                    continue
            # Coerce / validate ints
            elif expected_type is int:
                if isinstance(value, str):
                    try:
                        value = int(value)
                    except (ValueError, TypeError):
                        continue
                elif isinstance(value, int) and not isinstance(value, bool):
                    value = int(value)
                else:
                    continue
            # Strings
            elif expected_type is str and not isinstance(value, str):
                value = str(value)

            config[key] = value
