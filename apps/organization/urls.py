"""apps/organization/urls.py"""
from django.urls import path
from . import views

app_name = "organization"

urlpatterns = [
    path("setup/", views.OrganizationSetupView.as_view(), name="setup"),
    path("delete/", views.OrganizationDeleteView.as_view(), name="delete"),
    path("", views.OrganizationDetailView.as_view(), name="index"),
]
