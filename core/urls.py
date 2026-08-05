"""
core/urls.py

Advance Billing — Root URL Configuration
==========================================
All application routes are registered here.
URLs are namespaced per app for clean reversals in templates.

Route table:
  /                    → landing page
  /about/              → landing page (about section anchor)
  /features/           → landing page (features section anchor)
  /contact/            → coming soon
  /login/              → authentication
  /signup/             → authentication
  /logout/             → authentication
  /verify-email/       → authentication
  /forgot-password/    → authentication
  /reset-password/     → authentication
  /dashboard/          → dashboard (login required)
  /customers/          → customers (login required)
  /products/           → products  (login required)
  /invoices/           → billing   (login required)
  /organization/       → organization (login required)
  /settings/           → settings_app (login required)
  /health/             → common (public — health check)
  /admin/              → Django admin

All unrecognized URLs → custom 404 page
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

# Custom error handlers — must be registered here
handler404 = "apps.common.views.error_404"
handler500 = "apps.common.views.error_500"

urlpatterns = [
    # =========================================================================
    # Admin
    # =========================================================================
    path("admin/", admin.site.urls),

    # =========================================================================
    # Public Landing Pages
    # =========================================================================
    path("", include("apps.common.urls_landing")),

    # =========================================================================
    # Authentication
    # =========================================================================
    path("", include("apps.authentication.urls")),

    # =========================================================================
    # Dashboard (login required)
    # =========================================================================
    path("dashboard/", include("apps.dashboard.urls", namespace="dashboard")),

    # =========================================================================
    # Business Modules (login required — some show "Coming Soon" in phase 1)
    # =========================================================================
    path("customers/", include("apps.customers.urls", namespace="customers")),
    path("products/", include("apps.products.urls", namespace="products")),
    path("invoices/", include("apps.billing.urls", namespace="billing")),
    path("organization/", include("apps.organization.urls", namespace="organization")),
    path("settings/", include("apps.settings_app.urls", namespace="settings_app")),

    # =========================================================================
    # Common Utilities
    # =========================================================================
    path("", include("apps.common.urls")),
]

# =============================================================================
# Static & Media Files (development only)
# =============================================================================
# In production, WhiteNoise serves static files and Cloudinary serves media.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    # Optional: Django Debug Toolbar (when installed in development)
    try:
        import debug_toolbar  # noqa: F401
        urlpatterns = [
            path("__debug__/", include("debug_toolbar.urls")),
        ] + urlpatterns
    except ImportError:
        pass

# =============================================================================
# Admin Customization
# =============================================================================
admin.site.site_header = "Advance Billing Administration"
admin.site.site_title = "Advance Billing Admin"
admin.site.index_title = "Welcome to Advance Billing Admin"
