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
from apps.invoices.services.bill_serializer import serialize_bill_for_render


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
    "show_payment_info":    True,
    "show_page_numbers":    True,
    "show_print_date":      True,
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


class InvoicePreviewService:

    # ------------------------------------------------------------------
    # resolve_render_config
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_render_config(
        template_slug: str,
        user,
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

        Keys not declared in BillTemplate.default_config are stripped from
        layers 4 and 5 to ensure a template only receives what it supports.
        Falls back to _GLOBAL_DEFAULTS on missing/invalid values.

        Returns
        -------
        dict — clean, validated config ready to pass as ``{{ config }}`` in template.
        """
        from apps.settings_app.models import BillTemplate, UserBillPreference

        # --- Layer 1: global defaults ---
        config = dict(_GLOBAL_DEFAULTS)

        # --- Layer 2: BillTemplate.default_config ---
        try:
            bt = BillTemplate.objects.get(slug=template_slug)
            allowed_keys = bt.get_allowed_config_keys()
            config.update(bt.default_config)
        except BillTemplate.DoesNotExist:
            bt = None
            allowed_keys = set(_GLOBAL_DEFAULTS.keys())

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
        Single entry point for rendering ANY of the 8 templates to PDF.

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
        import weasyprint

        context = {
            **bill_data,        # bill, company, customer, items, gst_summary
            "config":       config,
            "layout_frame": layout_frame,
            "org":          org,
            # Legacy keys kept for backward-compat with any remaining old references
            "prefs":        config,
            "invoice":      bill_data.get("bill", {}),
            "customer":     bill_data.get("customer", {}),
            "items":        bill_data.get("items", []),
            "company":      bill_data.get("company", {}),
        }

        html_string = render_to_string(template_file_path, context)

        pdf_bytes = weasyprint.HTML(
            string=html_string,
            base_url="file://",
        ).write_pdf()

        return pdf_bytes

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
                    "logo_url": f"file://{org_data['logo'].path}" if org_data.get("logo") else None,
                    "signature_url": f"file://{org_data['signature'].path}" if org_data.get("signature") else None,
                    "letterhead_url": f"file://{org_data['letterhead'].path}" if org_data.get("letterhead") else None,
                }
                if org_data["default_bank"]:
                    company["bank_name"] = org_data["default_bank"].bank_name
                    company["acc_no"] = org_data["default_bank"].account_number
                    company["ifsc"] = org_data["default_bank"].ifsc_code
                org_obj = org_data["organization"]
            else:
                company = SampleDataService.sample_company()
                org_obj = None

        if custom_prefs is not None:
            prefs = custom_prefs
        else:
            prefs_obj = DocumentPreference.objects.filter(user=user).values().first()
            prefs = prefs_obj if prefs_obj else {}

        frame = PrintableFrameBuilder.build_frame(org_obj, prefs)

        invoice  = SampleDataService.sample_invoice(user)
        customer = SampleDataService.sample_customer()
        items    = SampleDataService.sample_items()

        # Build canonical bill data (new key; old keys kept for compat)
        canonical = serialize_bill_for_render(invoice, customer, items, company, org_obj)

        context = {
            # --- Canonical keys (used by new templates) ---
            **canonical,        # bill, company, customer, items, gst_summary
            "config":       prefs,
            "layout_frame": frame,
            "org":          org_obj,
            # --- Legacy keys (used by old/partial templates) ---
            "invoice":      invoice,
            "prefs":        prefs,
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
        "show_payment_info":     "show_payment_info",
        "show_page_numbers":     "show_page_numbers",
        "show_print_date":       "show_print_date",
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
