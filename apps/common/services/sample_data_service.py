"""
apps/common/services/sample_data_service.py
"""

class SampleDataService:
    @staticmethod
    def sample_customer():
        return {
            "name": "Acme Corp (Sample Customer)",
            "address": "123 Business Rd, Tech Park",
            "city": "Mumbai",
            "state": "Maharashtra",
            "gstin": "27AADCB2230M1Z2"
        }

    @staticmethod
    def sample_invoice(user=None):
        from django.conf import settings
        import os
        placeholder_img = os.path.join(settings.BASE_DIR, 'static', 'branding', 'apple-touch-icon.png')
        img_url = f"file://{placeholder_img}" if os.path.exists(placeholder_img) else None

        if user:
            from apps.settings_app.models import InvoicePreference
            inv_pref, _ = InvoicePreference.objects.get_or_create(user=user)
            preview_number = inv_pref.get_preview_number()
            default_notes = inv_pref.default_notes
            default_terms = inv_pref.default_terms
            default_currency = inv_pref.default_currency
        else:
            preview_number = "INV-0001"
            default_notes = "Thank you for your business."
            default_terms = "Payment due within 15 days. Subject to local jurisdiction."
            default_currency = "INR"

        return {
            "number": preview_number,
            "date": "07 Aug 2026",
            "due_date": "22 Aug 2026",
            "place_of_supply": "29-KARNATAKA",
            "subtotal": 5000.00,
            "tax_total": 900.00,
            "total": 5900.00,
            "grand_total": 5900.00,
            "amount_payable": 5900.00,
            "amount_paid": 0.00,
            "amount_due": 5900.00,
            "amount_in_words": "Five Thousand Nine Hundred Rupees Only",
            "notes": default_notes,
            "terms": default_terms,
            "currency": default_currency,
            "qr_code_url": img_url,
        }

    @staticmethod
    def sample_invoice_dict():
        return SampleDataService.sample_invoice(user=None)

    @staticmethod
    def sample_items():
        return [
            {"name": "Web Design Services", "hsn": "9983", "quantity": 1, "rate": 3000, "tax_pct": 18, "amount": 3000},
            {"name": "Server Hosting (Annual)", "hsn": "9983", "quantity": 1, "rate": 2000, "tax_pct": 18, "amount": 2000},
        ]
        
    @staticmethod
    def sample_company():
        from django.conf import settings
        import os
        
        # Use a placeholder image for demo purposes if it exists
        placeholder_img = os.path.join(settings.BASE_DIR, 'static', 'branding', 'logo-light.png')
        img_url = f"file://{placeholder_img}" if os.path.exists(placeholder_img) else None

        return {
            "name": "Acme Global Solutions (Demo)",
            "address": "456 Corporate Boulevard, Floor 5",
            "city": "Bengaluru",
            "state": "Karnataka",
            "gstin": "29AABCT1332L1Z9",
            "email": "billing@acmeglobal.demo",
            "phone": "+91 98765 43210",
            "logo_url": img_url,
            "signature_url": img_url,
            "letterhead_url": None,
            "signature_mode": "image",
            "authorized_signatory_name": "Acme Global Solutions",
            "show_computer_generated_disclaimer": False,
            "bank_name": "Demo Bank of India",
            "acc_no": "1234567890123",
            "ifsc": "DEMO0001234"
        }
