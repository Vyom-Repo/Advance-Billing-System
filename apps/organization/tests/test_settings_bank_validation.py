"""
apps/organization/tests/test_settings_bank_validation.py

Unit tests for Bank Details validation, normalization, and Organization settings changes.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.organization.models import Organization, BankAccount
from apps.organization.forms import BankAccountForm

User = get_user_model()


class BankDetailsValidationTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser_bank",
            email="testuser_bank@example.com",
            password="Password123!"
        )
        self.org = Organization.objects.create(
            owner=self.user,
            business_name="Samrudhi Enterprises",
            business_email="info@samrudhi.demo"
        )
        self.client.force_login(self.user)

    def test_bank_name_uppercase_normalization(self):
        """Test Bank Name is normalized to uppercase upon form validation and model save."""
        form = BankAccountForm(data={
            "bank_name": "hdfc bank",
            "account_name": "Samrudhi Enterprises",
            "account_number": "987654321012",
            "ifsc_code": "HDFC0001234",
            "branch": "Main Branch"
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["bank_name"], "HDFC BANK")

        account = BankAccount.objects.create(
            organization=self.org,
            bank_name="union bank of india",
            account_name="Samrudhi Enterprises",
            account_number="4324234323",
            ifsc_code="UBIN0232132",
            branch="Main Branch"
        )
        account.refresh_from_db()
        self.assertEqual(account.bank_name, "UNION BANK OF INDIA")

    def test_account_number_preserves_leading_zeros_and_string_type(self):
        """Test Account Number is preserved as string with leading zeros."""
        form = BankAccountForm(data={
            "bank_name": "STATE BANK OF INDIA",
            "account_name": "Samrudhi Enterprises",
            "account_number": "000123456789",
            "ifsc_code": "SBIN0001234",
            "branch": "Bengaluru Main",
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["account_number"], "000123456789")
        self.assertIsInstance(form.cleaned_data["account_number"], str)

    def test_account_number_validation_max_18_digits(self):
        """Test strict application-level account number validation (max 18 digits, digits only)."""
        # Valid 18 digits
        form_18 = BankAccountForm(data={
            "bank_name": "HDFC BANK",
            "account_name": "Samrudhi Enterprises",
            "account_number": "123456789012345678",
            "ifsc_code": "HDFC0001234",
            "branch": "Main Branch",
        })
        self.assertTrue(form_18.is_valid(), form_18.errors)

        # Invalid cases
        invalid_cases = [
            ("1234567890123456789", "Account number cannot exceed 18 digits."),  # 19 digits
            ("12345ABC678", "Account number must contain digits only."),           # Alphabetic
            ("1234 5678", "Account number must contain digits only."),             # Spaces
        ]

        for bad_acc, expected_error in invalid_cases:
            form = BankAccountForm(data={
                "bank_name": "ICICI BANK",
                "account_name": "Samrudhi Enterprises",
                "account_number": bad_acc,
                "ifsc_code": "ICIC0001234",
                "branch": "Main Branch",
            })
            self.assertFalse(form.is_valid(), f"Expected account {bad_acc} to fail.")
            self.assertIn(expected_error, str(form.errors.get("account_number")))

    def test_ifsc_code_structural_validation_and_normalization(self):
        """Test IFSC structural validation rules and uppercase normalization."""
        # Lowercase valid input
        form_lower = BankAccountForm(data={
            "bank_name": "HDFC BANK",
            "account_name": "Samrudhi Enterprises",
            "account_number": "123456789012",
            "ifsc_code": "abcd0001234",
            "branch": "Main Branch",
        })
        self.assertTrue(form_lower.is_valid(), form_lower.errors)
        self.assertEqual(form_lower.cleaned_data["ifsc_code"], "ABCD0001234")

        # Invalid lengths and structures
        invalid_ifsc_cases = [
            ("UNIN1234", "Enter a valid 11-character IFSC code."),
            ("HDFC1234567", "IFSC must contain 4 letters, followed by 0, followed by 6 alphanumeric characters."),
            ("12340001234", "IFSC must contain 4 letters, followed by 0, followed by 6 alphanumeric characters."),
            ("HDFC000123", "Enter a valid 11-character IFSC code."),
            ("HDFC00012345", "Enter a valid 11-character IFSC code."),
            ("HDFC-001234", "IFSC must contain 4 letters, followed by 0, followed by 6 alphanumeric characters."),
            ("HDFC 001234", "IFSC must contain 4 letters, followed by 0, followed by 6 alphanumeric characters."),
        ]

        for code, expected_error in invalid_ifsc_cases:
            form = BankAccountForm(data={
                "bank_name": "HDFC BANK",
                "account_name": "Samrudhi Enterprises",
                "account_number": "123456789012",
                "ifsc_code": code,
                "branch": "Main Branch",
            })
            self.assertFalse(form.is_valid(), f"Expected {code} to fail validation.")
            self.assertIn(expected_error, str(form.errors.get("ifsc_code")))

    def test_branch_field_is_required(self):
        """Test Branch field is mandatory and rejects empty/whitespace input."""
        # Valid branch
        form_valid = BankAccountForm(data={
            "bank_name": "AXIS BANK",
            "account_name": "Samrudhi Enterprises",
            "account_number": "91801001234567",
            "ifsc_code": "UTIB0000001",
            "branch": "Ahmedabad",
        })
        self.assertTrue(form_valid.is_valid(), form_valid.errors)

        # Empty and whitespace branch
        for bad_branch in ["", "   "]:
            form_invalid = BankAccountForm(data={
                "bank_name": "AXIS BANK",
                "account_name": "Samrudhi Enterprises",
                "account_number": "91801001234567",
                "ifsc_code": "UTIB0000001",
                "branch": bad_branch,
            })
            self.assertFalse(form_invalid.is_valid())
            self.assertIn("Branch is required.", str(form_invalid.errors.get("branch")))

    def test_terms_and_conditions_save_and_persistence(self):
        """Test Terms & Conditions changes persist via Organization settings POST and reload."""
        url = reverse("organization:index")
        response = self.client.post(url, data={
            "business_name": "Samrudhi Enterprises",
            "business_email": "info@samrudhi.demo",
            "address_line_1": "123 Business Park",
            "city": "Bengaluru",
            "state": "Karnataka",
            "pincode": "560001",
            "country": "India",
            "letterhead_header_offset": 50,
            "letterhead_footer_offset": 30,
            "is_gst_registered": "False",
            "terms_and_conditions": "New Invoice Terms: Payment due in 15 days.",
            "signature_mode": "authorized_signatory",
            "authorized_signatory_name": "Samrudhi Enterprises",
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.org.refresh_from_db()
        self.assertEqual(self.org.terms_and_conditions, "New Invoice Terms: Payment due in 15 days.")

        # Confirm GET request renders persisted terms
        get_response = self.client.get(url)
        self.assertContains(get_response, "New Invoice Terms: Payment due in 15 days.")
