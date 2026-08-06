"""
apps/organization/middleware.py
"""
import re
from django.shortcuts import redirect
from django.urls import reverse

class RequireOrganizationMiddleware:
    """
    Middleware that ensures authenticated users have set up an organization
    before accessing the main application routes.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that do not require an organization setup
        self.exempt_paths = [
            re.compile(r"^/login/"),
            re.compile(r"^/logout/"),
            re.compile(r"^/signup/"),
            re.compile(r"^/verify-email/"),
            re.compile(r"^/forgot-password/"),
            re.compile(r"^/reset-password/"),
            re.compile(r"^/organization/setup/"),
            re.compile(r"^/settings/"),
            re.compile(r"^/admin/"),
            re.compile(r"^/static/"),
            re.compile(r"^/media/"),
            re.compile(r"^/health/"),
            re.compile(r"^/$"),
            re.compile(r"^/about/"),
            re.compile(r"^/features/"),
            re.compile(r"^/contact/"),
        ]

    def __call__(self, request):
        if request.user.is_authenticated:
            path = request.path_info
            
            is_exempt = any(m.match(path) for m in self.exempt_paths)
            
            if not is_exempt:
                # Check if user has an organization
                if not hasattr(request.user, 'organization'):
                    return redirect(reverse('organization:setup'))
                    
        response = self.get_response(request)
        return response
