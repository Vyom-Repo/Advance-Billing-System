"""
apps/organization/tests/test_gst_validator.py
"""
from django.test import TestCase
from apps.organization.services import LocalGSTValidator

class LocalGSTValidatorTests(TestCase):
    def test_valid_gstin(self):
        result = LocalGSTValidator.validate("24ABCDE1234F1Z5")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["pan"], "ABCDE1234F")
        self.assertEqual(result["state_code"], "24")
        self.assertEqual(result["state_name"], "Gujarat")
        
    def test_invalid_length(self):
        result = LocalGSTValidator.validate("24ABCDE1234F1Z")
        self.assertFalse(result["is_valid"])
        self.assertEqual(result["error"], "GSTIN must be exactly 15 characters long.")
        
    def test_invalid_format(self):
        result = LocalGSTValidator.validate("241234E1234F1Z5")
        self.assertFalse(result["is_valid"])
        self.assertEqual(result["error"], "Invalid GSTIN format.")
        
    def test_empty_gstin(self):
        result = LocalGSTValidator.validate("")
        self.assertFalse(result["is_valid"])
