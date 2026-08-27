def demo_context(request):
    """
    Context processor injecting `is_demo_mode` flag globally when user is in the interactive demo environment.
    """
    return {
        "is_demo_mode": bool(request.session.get("is_demo_mode", False)),
    }
