"""apps/products/urls.py"""
from django.urls import path
from . import views

app_name = "products"

urlpatterns = [
    path("", views.ProductsComingSoon.as_view(), name="index"),
]
