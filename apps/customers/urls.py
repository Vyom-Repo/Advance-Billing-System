"""
apps/customers/urls.py — Customer Routing
"""
from django.urls import path
from . import views

app_name = "customers"

urlpatterns = [
    path("", views.CustomerListView.as_view(), name="index"),
    path("create/", views.CustomerCreateView.as_view(), name="create"),
    path("<uuid:uuid>/", views.CustomerDetailView.as_view(), name="detail"),
    path("<uuid:uuid>/edit/", views.CustomerUpdateView.as_view(), name="edit"),
    path("<uuid:uuid>/delete/", views.CustomerDeleteView.as_view(), name="delete"),
]
