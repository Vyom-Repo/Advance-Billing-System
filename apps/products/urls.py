"""
apps/products/urls.py — Product URL Routing

Uses stable UUID-based URLs for individual product operations.
Integer primary keys are never exposed in product-facing URLs.
"""
from django.urls import path
from . import views

app_name = "products"

urlpatterns = [
    path("",                       views.ProductListView.as_view(),   name="index"),
    path("create/",                views.ProductCreateView.as_view(), name="create"),
    path("<uuid:uuid>/",           views.ProductDetailView.as_view(), name="detail"),
    path("<uuid:uuid>/edit/",      views.ProductUpdateView.as_view(), name="edit"),
    path("<uuid:uuid>/delete/",    views.ProductDeleteView.as_view(), name="delete"),
]
