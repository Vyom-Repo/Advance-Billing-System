"""
apps/common/tests/test_production_cache_config.py

Unit tests verifying production Redis cache configuration and django_ratelimit compatibility.
"""

import os
from unittest import TestCase, mock
from django.core.exceptions import ImproperlyConfigured
from django_ratelimit.checks import check_caches


class ProductionCacheConfigTest(TestCase):
    """
    Verifies production cache settings requirements:
    1. Raises ImproperlyConfigured if REDIS_URL is missing in production.
    2. Configures django_redis.cache.RedisCache when REDIS_URL is provided.
    3. Guarantees django_ratelimit system check E003 is resolved for production settings.
    """

    def test_production_settings_raises_if_redis_url_missing(self):
        """Production settings must raise ImproperlyConfigured if REDIS_URL is not set."""
        env_dict = {
            "ALLOWED_HOSTS": "localhost,advancebilling.in",
            "DATABASE_URL": "postgresql://user:pass@localhost:5432/dbname",
            "EMAIL_HOST": "smtp.example.com",
            "EMAIL_HOST_USER": "user",
            "EMAIL_HOST_PASSWORD": "password",
            "SECRET_KEY": "test-secret-key-production-verification",
        }
        with mock.patch.dict(os.environ, env_dict, clear=True):
            import importlib
            import core.settings.production
            with self.assertRaises(ImproperlyConfigured) as cm:
                importlib.reload(core.settings.production)
            self.assertIn("REDIS_URL", str(cm.exception))

    def test_production_settings_configures_redis_cache(self):
        """Production settings configures django_redis and resolves django_ratelimit E003."""
        env_dict = {
            "ALLOWED_HOSTS": "localhost,advancebilling.in",
            "DATABASE_URL": "postgresql://user:pass@localhost:5432/dbname",
            "EMAIL_HOST": "smtp.example.com",
            "EMAIL_HOST_USER": "user",
            "EMAIL_HOST_PASSWORD": "password",
            "SECRET_KEY": "test-secret-key-production-verification",
            "REDIS_URL": "redis://127.0.0.1:6379/0",
        }
        with mock.patch.dict(os.environ, env_dict, clear=True):
            import importlib
            import core.settings.production
            prod_settings = importlib.reload(core.settings.production)

            self.assertEqual(
                prod_settings.CACHES["default"]["BACKEND"],
                "django_redis.cache.RedisCache",
            )
            self.assertEqual(
                prod_settings.CACHES["default"]["LOCATION"],
                "redis://127.0.0.1:6379/0",
            )

            # Verify system check E003 is not raised
            with mock.patch("django.conf.settings.CACHES", prod_settings.CACHES):
                class DummyApp:
                    pass
                errors = check_caches(DummyApp)
                e003_errors = [e for e in errors if e.id == "django_ratelimit.E003"]
                self.assertEqual(len(e003_errors), 0)
