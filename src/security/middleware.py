import logging

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from security.clientIp import extractClientIp, isTrustedProxy
from security.rateLimiter import IpRateLimiter

logger = logging.getLogger(__name__)

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

    # Liveness and API docs stay reachable even while a bucket is blocked.
    # Behind a proxy that is not in TRUSTED_PROXIES every client collapses into
    # one bucket, and a health check that answers 429 makes an orchestrator
    # recycle a container that is actually fine.
    _EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self._EXEMPT_PATHS:
            return await call_next(request)

        ip = self._extractIp(request)

        allowed, reason, retryAfter = await _ipLimiter.check(ip)

        if not allowed:
            return JSONResponse(
                status_code = 429,
                content     = {
                    "errorCode": "RATE_LIMIT_EXCEEDED",
                    "message":   reason
                },
                headers = {"Retry-After": str(retryAfter)}
            )

        return await call_next(request)


    def _extractIp(self, request: Request) -> str:
        """Resolve the client IP. Shared with slowapi's key_func — see clientIp."""
        return extractClientIp(request)


    @staticmethod
    def _isTrustedProxy(ip: str | None) -> bool:
        return isTrustedProxy(ip)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Registration in main.py:
        app.add_middleware(SecurityHeadersMiddleware)
    """

    _DOCS_PATHS = {"/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            response = await call_next(request)
        except Exception:
            # Log here (this is the innermost frame that still sees the original
            # traceback) and re-raise so ServerErrorMiddleware can build the
            # response through the app's exception handler, which includes the
            # traceback in dev. Swallowing it here made every 500 invisible.
            logger.exception("Unhandled error on %s %s", request.method, request.url.path)
            raise

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