"""
core/settings/base.py

Advance Billing — Base Settings
================================
Shared configuration inherited by both development.py and production.py.
All secrets and environment-specific values come from environment variables.

Never import this file directly. Import development.py or production.py.
The DJANGO_ENV environment variable controls which settings file is loaded.
"""

import os
from pathlib import Path

import environ

# =============================================================================
# PATHS
# =============================================================================

# Build paths relative to the project root (two levels up from this file)
# core/settings/base.py → core/settings → core → project_root
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# =============================================================================
# ENVIRONMENT VARIABLE LOADING
# =============================================================================

env = environ.Env(
    # Declare type casts and defaults for all environment variables.
    # Missing required variables without defaults will raise ImproperlyConfigured.

    # Django core
    DEBUG=(bool, False),
    SECRET_KEY=(str, ""),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),

    # Database & Cache
    DATABASE_URL=(str, ""),
    REDIS_URL=(str, ""),


    # Timezone
    TIME_ZONE=(str, "Asia/Kolkata"),

    # Email
    EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    EMAIL_HOST=(str, ""),
    EMAIL_PORT=(int, 587),
    EMAIL_USE_TLS=(bool, True),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    DEFAULT_FROM_EMAIL=(str, "Advance Billing <noreply@advancebilling.in>"),
    SERVER_EMAIL=(str, "Advance Billing <noreply@advancebilling.in>"),
    SUPPORT_EMAIL=(str, "advancebillingbyvyom@gmail.com"),

    # Cloudinary
    CLOUDINARY_CLOUD_NAME=(str, ""),
    CLOUDINARY_API_KEY=(str, ""),
    CLOUDINARY_API_SECRET=(str, ""),

    # Static & Media
    STATIC_URL=(str, "/static/"),
    STATIC_ROOT=(str, str(BASE_DIR / "staticfiles")),
    MEDIA_URL=(str, "/media/"),
    MEDIA_ROOT=(str, str(BASE_DIR / "media")),

    # Security (production values)
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
    SECURE_SSL_REDIRECT=(bool, False),

    # Render
    RENDER_EXTERNAL_HOSTNAME=(str, ""),

    # Internal
    DJANGO_ENV=(str, "development"),
)

# Read the .env file if it exists (development only; production uses system env vars)
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

# =============================================================================
# SECURITY
# =============================================================================

SECRET_KEY = env("SECRET_KEY")

# Validate SECRET_KEY is present — it is non-negotiable
if not SECRET_KEY:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        "SECRET_KEY environment variable is not set. "
        "Add SECRET_KEY to your .env file or environment."
    )

DEBUG = env("DEBUG")

ALLOWED_HOSTS: list[str] = env("ALLOWED_HOSTS")

# Automatically add Render external hostname to ALLOWED_HOSTS
_render_hostname = env("RENDER_EXTERNAL_HOSTNAME")
if _render_hostname and _render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_hostname)

CSRF_TRUSTED_ORIGINS: list[str] = env("CSRF_TRUSTED_ORIGINS")

# Add Render hostname to CSRF trusted origins automatically
if _render_hostname:
    _render_origin = f"https://{_render_hostname}"
    if _render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(_render_origin)

# =============================================================================
# APPLICATION DEFINITION
# =============================================================================

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "cloudinary",
    "cloudinary_storage",
    "django_ratelimit",
    "csp",
]

LOCAL_APPS = [
    "apps.common",
    "apps.authentication",
    "apps.dashboard",
    "apps.customers",
    "apps.products",
    "apps.billing",
    "apps.organization",
    "apps.settings_app",
    "apps.admin_portal",
    "apps.demo",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# =============================================================================
# MIDDLEWARE
# =============================================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",          # Serve static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",                         # Content Security Policy
    "apps.organization.middleware.RequireOrganizationMiddleware", # Require Organization
]

# =============================================================================
# URL CONFIGURATION
# =============================================================================

ROOT_URLCONF = "core.urls"

# =============================================================================
# TEMPLATES
# =============================================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],                   # Global templates directory
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Custom context processors
                "apps.common.context_processors.theme_context",
                "apps.common.context_processors.app_context",
                "apps.organization.context_processors.organization_context",
                "apps.demo.context_processors.demo_context",
            ],
        },
    },
]

# =============================================================================
# WSGI / ASGI
# =============================================================================

WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

# =============================================================================
# DATABASE
# =============================================================================
# Concrete database config is set in development.py and production.py.
# Base leaves it as an empty dict; subclasses must override.
DATABASES: dict = {}

# =============================================================================
# AUTHENTICATION
# =============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/"

# =============================================================================
# INTERNATIONALIZATION
# =============================================================================

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE")
USE_I18N = True
USE_TZ = True

# =============================================================================
# STATIC FILES
# =============================================================================

STATIC_URL = env("STATIC_URL")
STATIC_ROOT = env("STATIC_ROOT")

STATICFILES_DIRS = [
    BASE_DIR / "static",                                    # Project-level static files
]

STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# WhiteNoise compression and caching
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# =============================================================================
# MEDIA FILES
# =============================================================================

MEDIA_URL = env("MEDIA_URL")
MEDIA_ROOT = env("MEDIA_ROOT")

# Cloudinary configuration (used in production)
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": env("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": env("CLOUDINARY_API_KEY"),
    "API_SECRET": env("CLOUDINARY_API_SECRET"),
}

# =============================================================================
# EMAIL CONFIGURATION
# =============================================================================

EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = env("SERVER_EMAIL")
SUPPORT_EMAIL = env("SUPPORT_EMAIL")

# =============================================================================
# DEFAULT PRIMARY KEY
# =============================================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# =============================================================================
# SESSION
# =============================================================================

SESSION_COOKIE_AGE = 86400 * 14    # 14 days
SESSION_COOKIE_HTTPONLY = True
SESSION_SAVE_EVERY_REQUEST = False

# =============================================================================
# SECURITY SETTINGS (will be overridden in production)
# =============================================================================

SESSION_COOKIE_SECURE = env("SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = env("CSRF_COOKIE_SECURE")
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT")

# =============================================================================
# CONTENT SECURITY POLICY (django-csp)
# =============================================================================

CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = (
    "'self'",
    "'unsafe-inline'",                                      # Required for inline styles in templates
    "https://fonts.googleapis.com",
)
CSP_FONT_SRC = (
    "'self'",
    "https://fonts.gstatic.com",
)
CSP_SCRIPT_SRC = (
    "'self'",
    "'unsafe-inline'",
    "https://unpkg.com",                                    # Lucide Icons CDN
    "https://cdn.jsdelivr.net",                             # Chart.js CDN
)
CSP_IMG_SRC = (
    "'self'",
    "data:",
    "https://res.cloudinary.com",                           # Cloudinary media
)
CSP_CONNECT_SRC = ("'self'",)

# =============================================================================
# LOGGING
# =============================================================================

# Ensure logs directory exists
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "advance_billing.log",
            "maxBytes": 1024 * 1024 * 10,                  # 10 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
        "error_file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "errors.log",
            "maxBytes": 1024 * 1024 * 10,
            "backupCount": 5,
            "formatter": "verbose",
            "level": "ERROR",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console", "error_file"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console", "file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# =============================================================================
# CUSTOM ERROR HANDLERS
# =============================================================================

handler404 = "apps.common.views.error_404"
handler500 = "apps.common.views.error_500"

# =============================================================================
# APPLICATION-SPECIFIC SETTINGS
# =============================================================================

# Advance Billing project metadata
APP_NAME = "Advance Billing"
APP_TAGLINE = "GST Billing Made Simple for Indian Businesses"
APP_VERSION = "1.0.0"

# Supported GST slabs (as per Indian GST law)
GST_SLABS = [0, 0.1, 0.25, 1, 1.5, 3, 5, 6, 7.5, 12, 18, 28]

# Supported Indian states for IGST vs CGST/SGST determination
INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry",
]

# Theme configuration — architecture ready for multi-theme support
AVAILABLE_THEMES = [
    {"id": "bhagwa", "name": "Bhagwa (Saffron)", "default": True},
    {"id": "cyan", "name": "Cyan", "default": False},
    {"id": "light-blue", "name": "Light Blue", "default": False},
    {"id": "emerald", "name": "Emerald", "default": False},
    {"id": "purple", "name": "Purple", "default": False},
]

DEFAULT_THEME = "bhagwa"
