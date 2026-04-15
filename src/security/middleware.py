from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from security.rateLimiter import IpRateLimiter


# Global instance — shared across all requests
_ipLimiter = IpRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Global IP-based rate limiting middleware.

    Applied automatically to all routes.
    Returns 429 with a Retry-After header when the limit is exceeded.

    Registration in main.py:
        app.add_middleware(RateLimitMiddleware)
    """

    async def dispatch(self, request: Request, callNext):
        ip = self._extractIp(request)

        allowed, reason = _ipLimiter.check(ip)

        if not allowed:
            return JSONResponse(
                status_code = 429,
                content     = {
                    "errorCode": "RATE_LIMIT_EXCEEDED",
                    "message":   reason
                },
                headers = {"Retry-After": "60"}
            )

        return await callNext(request)


    def _extractIp(self, request: Request) -> str:
        """
        Extracts the real client IP, respecting reverse proxies.
        X-Forwarded-For is populated automatically by Vercel.
        """
        forwarded = request.headers.get("X-Forwarded-For")

        if forwarded:
            return forwarded.split(",")[0].strip()

        return request.client.host


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Registration in main.py:
        app.add_middleware(SecurityHeadersMiddleware)
    """

    _DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, callNext):
        response = await callNext(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"]        = "DENY"
        response.headers["X-XSS-Protection"]       = "1; mode=block"
        response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"

        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        if request.url.path in self._DOCS_PATHS:
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "object-src 'none'; "
                "frame-ancestors 'none';"
            )
        else:
            csp = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "object-src 'none'; "
                "frame-ancestors 'none';"
            )

        response.headers["Content-Security-Policy"] = csp

        return response