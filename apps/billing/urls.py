"""apps/billing/urls.py"""
from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("", views.BillingComingSoon.as_view(), name="index"),
]
