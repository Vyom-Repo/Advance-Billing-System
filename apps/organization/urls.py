"""apps/organization/urls.py"""
from django.urls import path
from . import views

app_name = "organization"

urlpatterns = [
    path("", views.OrganizationComingSoon.as_view(), name="index"),
]
