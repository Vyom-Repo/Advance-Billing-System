"""
apps/common/services/rate_limit.py

Rate Limiting Response Helper Service for Advance Billing.
Computes remaining window time (retry_after) and constructs standardized HTTP 429 responses
with Retry-After response headers and JSON/plain text payloads.
"""

from django.http import HttpResponse, JsonResponse


def get_ratelimit_retry_after(request, fn=None, key=None, rate=None) -> int:
    retry_after = 60
    if rate:
        if "/h" in rate:
            retry_after = 3600
        elif "/d" in rate:
            retry_after = 86400

    if fn and key and rate:
        try:
            from django_ratelimit.core import get_usage
            usage = get_usage(request, fn=fn, key=key, rate=rate)
            if usage and "time_left" in usage and usage["time_left"] > 0:
                return max(1, int(usage["time_left"]))
        except Exception:
            pass

    return retry_after


def build_ratelimit_429_response(
    request,
    fn=None,
    key=None,
    rate=None,
    is_json=False,
    custom_message=None,
) -> HttpResponse:
    retry_after = get_ratelimit_retry_after(request, fn=fn, key=key, rate=rate)
    
    msg = custom_message or f"Rate limit exceeded. Please wait {retry_after} seconds before trying again."

    if is_json:
        response = JsonResponse(
            {
                "success": False,
                "error": "Rate limit exceeded",
                "message": msg,
                "retry_after": retry_after,
            },
            status=429,
        )
    else:
        response = HttpResponse(msg, status=429, content_type="text/plain")

    response["Retry-After"] = str(retry_after)
    return response
