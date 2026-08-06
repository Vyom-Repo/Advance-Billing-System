"""
apps/organization/services.py
"""
import re
from typing import Dict, Any

class LocalGSTValidator:
    """
    Validates Indian GSTIN (Goods and Services Tax Identification Number) locally.
    Extracts PAN and State Code without any external API calls.
    """
    
    # 2 digits (state code), 10 alphanumeric (PAN), 1 alphanumeric (entity number), 1 'Z' (default), 1 alphanumeric (checksum)
    GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}[Z]{1}[0-9A-Z]{1}$")

    STATE_CODES = {
        "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
        "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
        "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
        "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam", "19": "West Bengal",
        "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
        "25": "Daman and Diu", "26": "Dadra and Nagar Haveli", "27": "Maharashtra", "28": "Andhra Pradesh (Old)",
        "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu",
        "34": "Puducherry", "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh",
        "38": "Ladakh", "97": "Other Territory"
    }

    @classmethod
    def validate(cls, gstin: str) -> Dict[str, Any]:
        if not gstin:
            return {"is_valid": False, "error": "GSTIN is required."}
            
        gstin = gstin.strip().upper()
        
        if len(gstin) != 15:
            return {"is_valid": False, "error": "GSTIN must be exactly 15 characters long."}
            
        if not cls.GSTIN_REGEX.match(gstin):
            return {"is_valid": False, "error": "Invalid GSTIN format."}
            
        state_code = gstin[0:2]
        pan = gstin[2:12]
        state_name = cls.STATE_CODES.get(state_code, "Unknown State")
        
        return {
            "is_valid": True,
            "pan": pan,
            "state_code": state_code,
            "state_name": state_name
        }
