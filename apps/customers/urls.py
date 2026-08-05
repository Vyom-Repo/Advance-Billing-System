"""apps/customers/urls.py"""
from django.urls import path
from . import views

app_name = "customers"

urlpatterns = [
    path("", views.CustomersComingSoon.as_view(), name="index"),
]
