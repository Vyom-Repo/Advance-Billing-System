"""
apps/authentication/forms.py

Advance Billing — Authentication Forms
"""

from django import forms
from django.contrib.auth.models import User
from django.core.validators import EmailValidator


class SignupForm(forms.ModelForm):
    """
    New user registration form.
    Creates a Django User. Organization setup happens after email verification.
    """

    email = forms.EmailField(
        label="Email Address",
        validators=[EmailValidator()],
        widget=forms.EmailInput(attrs={
            "placeholder": "you@yourcompany.com",
            "autocomplete": "email",
            "class": "form-input",
        }),
    )
    password1 = forms.CharField(
        label="Password",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            "placeholder": "Minimum 8 characters",
            "autocomplete": "new-password",
            "class": "form-input",
        }),
    )
    password2 = forms.CharField(
        label="Confirm Password",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            "placeholder": "Repeat your password",
            "autocomplete": "new-password",
            "class": "form-input",
        }),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={
                "placeholder": "First Name",
                "autocomplete": "given-name",
                "class": "form-input",
            }),
            "last_name": forms.TextInput(attrs={
                "placeholder": "Last Name",
                "autocomplete": "family-name",
                "class": "form-input",
            }),
        }

    def clean_email(self) -> str:
        email = self.cleaned_data.get("email", "").lower().strip()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists. Please sign in."
            )
        return email

    def clean(self) -> dict:
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError({"password2": "Passwords do not match."})
        return cleaned_data

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        email = self.cleaned_data["email"]
        user.username = email
        user.email = email
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    """Simple email + password login form."""

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            "placeholder": "you@yourcompany.com",
            "autocomplete": "email",
            "class": "form-input",
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "placeholder": "Your password",
            "autocomplete": "current-password",
            "class": "form-input",
        }),
    )

    def clean_email(self) -> str:
        return self.cleaned_data.get("email", "").lower().strip()


class ForgotPasswordForm(forms.Form):
    """Request a password reset link by email."""

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            "placeholder": "you@yourcompany.com",
            "autocomplete": "email",
            "class": "form-input",
        }),
    )

    def clean_email(self) -> str:
        return self.cleaned_data.get("email", "").lower().strip()


class ResetPasswordForm(forms.Form):
    """Set a new password using a valid reset token."""

    password1 = forms.CharField(
        label="New Password",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            "placeholder": "Minimum 8 characters",
            "autocomplete": "new-password",
            "class": "form-input",
        }),
    )
    password2 = forms.CharField(
        label="Confirm New Password",
        min_length=8,
        widget=forms.PasswordInput(attrs={
            "placeholder": "Repeat your new password",
            "autocomplete": "new-password",
            "class": "form-input",
        }),
    )

    def clean(self) -> dict:
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password1")
        p2 = cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError({"password2": "Passwords do not match."})
        return cleaned_data
