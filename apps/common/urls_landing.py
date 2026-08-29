"""
apps/common/urls_landing.py — Landing/Public Page URLs
"""

from django.urls import path
from .views import LandingView, PrivacyPolicyView, TermsOfServiceView

urlpatterns = [
    path("", LandingView.as_view(), name="landing"),
    path("privacy/", PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("privacy-policy/", PrivacyPolicyView.as_view()),
    path("terms/", TermsOfServiceView.as_view(), name="terms_of_service"),
    path("terms-of-service/", TermsOfServiceView.as_view()),
    # These are anchor sections on the same landing page.
    # They redirect to the landing page — handled by JS smooth scroll.
    path("about/", LandingView.as_view(), name="about"),
    path("features/", LandingView.as_view(), name="features"),
    path("contact/", LandingView.as_view(), name="contact"),
]
