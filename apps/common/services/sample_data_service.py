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
    def sample_invoice(user):
        from apps.settings_app.models import InvoicePreference
        inv_pref, _ = InvoicePreference.objects.get_or_create(user=user)
        
        return {
            "number": inv_pref.get_preview_number(),
            "date": "07 Aug 2026",
            "due_date": "22 Aug 2026",
            "subtotal": 5000.00,
            "tax_total": 900.00,
            "total": 5900.00,
            "notes": inv_pref.default_notes,
            "terms": inv_pref.default_terms,
            "currency": inv_pref.default_currency,
        }

    @staticmethod
    def sample_items():
        return [
            {"name": "Web Design Services", "hsn": "9983", "quantity": 1, "rate": 3000, "tax_pct": 18, "amount": 3000},
            {"name": "Server Hosting (Annual)", "hsn": "9983", "quantity": 1, "rate": 2000, "tax_pct": 18, "amount": 2000},
        ]
        
    @staticmethod
    def sample_company():
        return {
            "name": "Your Company Name",
            "address": "Please configure your Organization settings.",
            "city": "",
            "state": "",
            "gstin": "",
            "email": "",
            "phone": ""
        }
