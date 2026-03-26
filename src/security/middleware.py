from fastapi        import Request
from fastapi.responses  import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from security.rateLimiter import IpRateLimiter


# Instância global — compartilhada entre todas as requisições
_ipLimiter = IpRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware global de rate limiting por IP.

    Aplicado em todas as rotas automaticamente.
    Retorna 429 com header Retry-After quando o limite é excedido.

    Registro no main.py:
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
        Extrai o IP real do cliente respeitando proxies.
        X-Forwarded-For é preenchido pela Vercel automaticamente.
        """
        forwarded = request.headers.get("X-Forwarded-For")

        if forwarded:
            return forwarded.split(",")[0].strip()

        return request.client.host


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware que adiciona headers de segurança em todas as respostas.

    Registro no main.py:
        app.add_middleware(SecurityHeadersMiddleware)
    """

    async def dispatch(self, request: Request, callNext):
        response = await callNext(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"]        = "DENY"
        response.headers["X-XSS-Protection"]       = "1; mode=block"
        response.headers["Referrer-Policy"]         = "strict-origin-when-cross-origin"

        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none';"
        )

        return response