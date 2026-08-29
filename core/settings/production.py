"""
core/settings/production.py

Advance Billing — Production Settings
=======================================
Inherits from base.py. Applies strict security and requires PostgreSQL.

Usage on Render:
    Set DJANGO_SETTINGS_MODULE=core.settings.production in environment.
    All required variables must be set in Render's environment configuration.

This file raises ImproperlyConfigured if critical production values are missing.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401, F403
from .base import env, BASE_DIR

# =============================================================================
# CORE
# =============================================================================

DEBUG = False

# ALLOWED_HOSTS must be explicitly set in production
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS must be set in production. "
        "Example: ALLOWED_HOSTS=advancebilling.in,www.advancebilling.in"
    )

# =============================================================================
# DATABASE (PostgreSQL required in production)
# =============================================================================

_database_url = env("DATABASE_URL")
if not _database_url:
    raise ImproperlyConfigured(
        "DATABASE_URL must be set in production. "
        "Example: DATABASE_URL=postgresql://user:password@host:5432/dbname"
    )

import dj_database_url  # noqa: E402

DATABASES = {
    "default": dj_database_url.parse(
        _database_url,
        conn_max_age=600,
        conn_health_checks=True,
    )
}
DATABASES["default"]["OPTIONS"] = DATABASES["default"].get("OPTIONS", {})
DATABASES["default"]["OPTIONS"]["connect_timeout"] = 10

# =============================================================================
# SECURITY (enforced in production)
# =============================================================================

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000             # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # Required on Render

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True         # Deprecated but harmless

# =============================================================================
# EMAIL (Brevo via SMTP in production)
# =============================================================================

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_TIMEOUT = env("EMAIL_TIMEOUT", default=10)

if not all([env("EMAIL_HOST"), env("EMAIL_HOST_USER"), env("EMAIL_HOST_PASSWORD")]):
    raise ImproperlyConfigured(
        "Email SMTP credentials (EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD) "
        "must be set in production."
    )

# =============================================================================
# MEDIA STORAGE (Cloudinary in production)
# =============================================================================

_cloudinary_cloud = env("CLOUDINARY_CLOUD_NAME")
_cloudinary_key = env("CLOUDINARY_API_KEY")
_cloudinary_secret = env("CLOUDINARY_API_SECRET")

if not all([_cloudinary_cloud, _cloudinary_key, _cloudinary_secret]):
    missing = [
        name for name, val in [
            ("CLOUDINARY_CLOUD_NAME", _cloudinary_cloud),
            ("CLOUDINARY_API_KEY", _cloudinary_key),
            ("CLOUDINARY_API_SECRET", _cloudinary_secret),
        ] if not val
    ]
    raise ImproperlyConfigured(
        f"Cloudinary media storage configuration missing in production. "
        f"The following environment variables must be set: {', '.join(missing)}. "
        f"Render's filesystem is ephemeral; persistent media storage requires Cloudinary."
    )

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
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"

# =============================================================================
# STATIC FILES (WhiteNoise in production)
# =============================================================================

# WhiteNoise is already configured in base.py middleware and STATICFILES_STORAGE.
# No additional CDN required for Render deployments.

# =============================================================================
# CACHE (Redis required in production for shared multi-worker rate limiting)
# =============================================================================

_redis_url = env("REDIS_URL")
if not _redis_url:
    raise ImproperlyConfigured(
        "REDIS_URL environment variable must be set in production. "
        "Example: REDIS_URL=redis://user:password@host:6379/0 or rediss://..."
    )

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": _redis_url,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "SOCKET_CONNECT_TIMEOUT": 5,
            "SOCKET_TIMEOUT": 5,
            "IGNORE_EXCEPTIONS": True,
        },
    }
}


# =============================================================================
# LOGGING (production: info level, no debug noise)
# =============================================================================

LOGGING["loggers"]["django"]["level"] = "WARNING"   # type: ignore[index]
LOGGING["loggers"]["apps"]["level"] = "INFO"         # type: ignore[index]

# =============================================================================
# PERFORMANCE
# =============================================================================

# Template caching — significantly improves response time
TEMPLATES[0]["APP_DIRS"] = False                     # type: ignore[index]
TEMPLATES[0]["OPTIONS"]["loaders"] = [               # type: ignore[index]
    (
        "django.template.loaders.cached.Loader",
        [
            "django.template.loaders.filesystem.Loader",
            "django.template.loaders.app_directories.Loader",
        ],
    )
]
