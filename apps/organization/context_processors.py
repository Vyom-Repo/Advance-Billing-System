"""
apps/organization/context_processors.py
"""

def organization_context(request):
    """
    Injects the user's organization into the template context globally.
    """
    if request.user.is_authenticated and hasattr(request.user, 'organization'):
        return {'user_org': request.user.organization}
    return {'user_org': None}
