"""
core/asgi.py

Advance Billing ASGI Application
==================================
ASGI config for Advance Billing. Exposes the ASGI callable as a module-level
variable named ``application``. Future-ready for WebSockets / async views.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.development")

application = get_asgi_application()
