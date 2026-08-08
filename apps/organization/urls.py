"""apps/organization/urls.py"""
from django.urls import path
from . import views

app_name = "organization"

urlpatterns = [
    path("setup/", views.OrganizationSetupView.as_view(), name="setup"),
    path("delete/", views.OrganizationDeleteView.as_view(), name="delete"),
    path("bank-account/add/", views.BankAccountCreateView.as_view(), name="bank_add"),
    path("bank-account/<int:pk>/edit/", views.BankAccountUpdateView.as_view(), name="bank_edit"),
    path("bank-account/<int:pk>/delete/", views.BankAccountDeleteView.as_view(), name="bank_delete"),
    path("bank-account/<int:pk>/default/", views.BankAccountDefaultView.as_view(), name="bank_default"),
    path("letterhead-preview/", views.OrganizationLetterheadPreviewView.as_view(), name="letterhead_preview"),
    path("", views.OrganizationDetailView.as_view(), name="index"),
]
