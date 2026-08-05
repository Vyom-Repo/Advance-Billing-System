"""
apps/common/templatetags/common_tags.py

Advance Billing — Custom Template Tags and Filters
====================================================
Reusable template tags available across all templates.

Usage in templates:
    {% load common_tags %}
    {{ amount|rupees }}
    {% active_link request 'dashboard:index' %}
"""

from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()


# =============================================================================
# FILTERS
# =============================================================================

@register.filter(name="rupees")
def rupees(value: float | int | str) -> str:
    """
    Formats a number as Indian Rupees with ₹ symbol and 2 decimal places.

    Usage:
        {{ invoice.total|rupees }}
        → ₹1,250.00
    """
    try:
        amount = float(value)
        return f"₹{amount:,.2f}"
    except (ValueError, TypeError):
        return "₹0.00"


@register.filter(name="gst_display")
def gst_display(value: float | int | str) -> str:
    """
    Formats a GST percentage for display.

    Usage:
        {{ product.gst_percentage|gst_display }}
        → 18%
    """
    try:
        return f"{float(value):.0f}%"
    except (ValueError, TypeError):
        return "0%"


# =============================================================================
# TAGS
# =============================================================================

@register.simple_tag(takes_context=True)
def active_link(context: dict, url_name: str, css_class: str = "active") -> str:
    """
    Returns css_class if the current request path matches the given URL name.
    Used to highlight active sidebar/nav links.

    Usage:
        {% active_link request 'dashboard:index' %}
        → "active" (or empty string)
    """
    request = context.get("request")
    if not request:
        return ""
    try:
        url = reverse(url_name)
        if request.path == url or request.path.startswith(url):
            return css_class
    except NoReverseMatch:
        pass
    return ""


@register.inclusion_tag("base/flash_messages.html", takes_context=True)
def show_messages(context: dict) -> dict:
    """
    Renders flash messages (Django messages framework).
    Maps Django message levels to CSS classes for the design system.

    Usage in base template:
        {% show_messages %}
    """
    return {"messages": context.get("messages", [])}


@register.inclusion_tag("common/logo.html")
def render_logo(css_class: str = "", style: str = "") -> dict:
    """
    Renders the master Advance Billing Indian Rupee (₹) Receipt Logo SVG.

    Usage:
        {% render_logo class="sidebar-logo-icon" style="width: 24px;" %}
    """
    return {
        "class": css_class,
        "style": style,
    }
