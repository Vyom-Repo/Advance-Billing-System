"""
apps/invoices/services/invoice_preview_service.py
"""
from apps.common.services.organization_service import OrganizationService
from apps.common.services.sample_data_service import SampleDataService
from apps.common.services.layout_engine import PrintableFrameBuilder
from apps.settings_app.models import DocumentPreference

class InvoicePreviewService:
    @staticmethod
    def get_preview_context(user, custom_prefs=None, preview_mode=None):
        """
        Merge organization data, invoice preferences, and sample/real data 
        into a single rendering context.
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

        context = {
            "invoice": SampleDataService.sample_invoice(user),
            "customer": SampleDataService.sample_customer(),
            "items": SampleDataService.sample_items(),
            "company": company,
            "org": org_obj,
            "prefs": prefs,
            "layout_frame": frame,
        }
        return context
