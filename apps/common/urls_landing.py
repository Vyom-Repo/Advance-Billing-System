"""
apps/common/urls_landing.py — Landing/Public Page URLs
"""

from django.urls import path
from .views import LandingView

urlpatterns = [
    path("", LandingView.as_view(), name="landing"),
    # These are anchor sections on the same landing page.
    # They redirect to the landing page — handled by JS smooth scroll.
    path("about/", LandingView.as_view(), name="about"),
    path("features/", LandingView.as_view(), name="features"),
    path("contact/", LandingView.as_view(), name="contact"),
]
