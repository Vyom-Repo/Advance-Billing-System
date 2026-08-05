"""
core/wsgi.py

Advance Billing WSGI Application
==================================
Exposes the WSGI callable as a module-level variable named ``application``.
Used by Gunicorn in production (see Procfile).
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.development")

application = get_wsgi_application()
