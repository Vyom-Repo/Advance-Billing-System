"""
apps/common/services/organization_service.py
"""

class OrganizationService:
    @staticmethod
    def get_company_assets(user):
        """
        Returns the company identity, assets, and branding for the user's organization.
        """
        from apps.organization.models import Organization
        
        org = Organization.objects.filter(owner=user).first()
        if not org:
            return None
            
        bank = org.bank_accounts.filter(is_default=True).first()
        if not bank:
            bank = org.bank_accounts.first()
            
        return {
            "organization": org,
            "business_name": org.business_name,
            "logo": org.logo if org.logo else None,
            "letterhead": org.letterhead if org.letterhead else None,
            "letterhead_header_offset": org.letterhead_header_offset,
            "letterhead_footer_offset": org.letterhead_footer_offset,
            "signature": org.signature if org.signature else None,
            "default_bank": bank,
            "gstin": org.gstin,
            "address_line_1": org.address_line_1,
            "address_line_2": org.address_line_2,
            "city": org.city,
            "state": org.state,
            "pincode": org.pincode,
            "country": org.country,
            "email": org.business_email,
            "phone": org.phone_number,
        }
