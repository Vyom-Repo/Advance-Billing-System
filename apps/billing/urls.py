"""apps/billing/urls.py — Invoice Routing (Phase 09)"""
from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    # Invoice CRUD
    path("", views.InvoiceListView.as_view(), name="index"),
    path("create/", views.InvoiceCreateView.as_view(), name="create"),
    path("<uuid:uuid>/", views.InvoiceDetailView.as_view(), name="detail"),
    path("<uuid:uuid>/edit/", views.InvoiceEditView.as_view(), name="edit"),
    path("<uuid:uuid>/delete/", views.InvoiceDeleteView.as_view(), name="delete"),
    # Lifecycle actions
    path("<uuid:uuid>/issue/", views.InvoiceIssueView.as_view(), name="issue"),
    path("<uuid:uuid>/cancel/", views.InvoiceCancelView.as_view(), name="cancel"),
    # Preview (Phase 10 entry point)
    path("<uuid:uuid>/preview/", views.InvoicePreviewView.as_view(), name="preview"),
    # Draft calculation preview (AJAX — display only, not persisted)
    path("<uuid:uuid>/preview-calc/", views.InvoicePreviewCalculationView.as_view(), name="preview_calc"),
    # JSON APIs (organization-scoped)
    path("api/customers/", views.CustomerSearchAPIView.as_view(), name="api_customers"),
    path("api/customers/<int:pk>/", views.CustomerDetailAPIView.as_view(), name="api_customer_detail"),
    path("api/products/", views.ProductSearchAPIView.as_view(), name="api_products"),
    path("api/products/<int:pk>/", views.ProductDetailAPIView.as_view(), name="api_product_detail"),

    # Session stash for Customer + / Product + return flow
    path("session/stash/", views.InvoiceSessionStashView.as_view(), name="session_stash"),
]
