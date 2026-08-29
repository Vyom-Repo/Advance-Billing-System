"""
core/settings/development.py

Advance Billing — Development Settings
========================================
Inherits from base.py. Overrides values appropriate for local development.

Usage:
    export DJANGO_SETTINGS_MODULE=core.settings.development
    python manage.py runserver

Or set DJANGO_ENV=development in your .env file.
"""

from .base import *  # noqa: F401, F403
from .base import env, BASE_DIR

# =============================================================================
# CORE
# =============================================================================

DEBUG = True

# In development, allow all local origins by default
ALLOWED_HOSTS = list(set(env("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "0.0.0.0"]) + ["localhost", "127.0.0.1", "0.0.0.0", "testserver"]))

# =============================================================================
# DATABASE
# =============================================================================
# In development: use SQLite if DATABASE_URL is not set.
# This means the project starts with zero configuration.

_database_url = env("DATABASE_URL", default="")

if _database_url:
    import dj_database_url

    DATABASES = {
        "default": dj_database_url.parse(
            _database_url,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    # SQLite fallback — no configuration required for local development
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# =============================================================================
# EMAIL
# =============================================================================
# Use console backend in development — all emails print to the terminal.
# Override with EMAIL_BACKEND in .env to test Brevo locally.

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

# =============================================================================
# SECURITY (relaxed for development)
# =============================================================================

SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# =============================================================================
# STATIC & MEDIA
# =============================================================================
# Use local filesystem for media in development by default.
# If Cloudinary credentials are provided in .env, activate Cloudinary for local testing.
_cloudinary_cloud = env("CLOUDINARY_CLOUD_NAME", default="")
_cloudinary_key = env("CLOUDINARY_API_KEY", default="")
_cloudinary_secret = env("CLOUDINARY_API_SECRET", default="")

if all([_cloudinary_cloud, _cloudinary_key, _cloudinary_secret]):
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": _cloudinary_cloud,
        "API_KEY": _cloudinary_key,
        "API_SECRET": _cloudinary_secret,
    }
    STORAGES = {
        "default": {
            "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"
else:
    STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# =============================================================================
# CACHE
# =============================================================================
# Use dummy cache in development — no Redis required.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-snowflake",
    }
}

# Silence django-ratelimit cache check in development since we use LocMemCache locally
SILENCED_SYSTEM_CHECKS = ["django_ratelimit.E003", "django_ratelimit.W001"]

# =============================================================================
# LOGGING (verbose for development)
# =============================================================================

LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # type: ignore[index]
LOGGING["loggers"]["django"]["level"] = "INFO"  # type: ignore[index]

# =============================================================================
# DEVELOPMENT UTILITIES
# =============================================================================

# Internal IPs for django-debug-toolbar (when installed)
INTERNAL_IPS = ["127.0.0.1", "localhost"]

# Show full error pages with tracebacks
DEBUG_PROPAGATE_EXCEPTIONS = False

# =============================================================================
# CSRF
# =============================================================================

CSRF_TRUSTED_ORIGINS = env(
    "CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:8000", "http://127.0.0.1:8000"],
)
