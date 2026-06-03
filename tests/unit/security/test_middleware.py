import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastapi.responses import JSONResponse


class TestRateLimitMiddleware:
    def _make_app(self, allowed=True):
        from security.middleware import RateLimitMiddleware
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)

        @app.get("/ping")
        def ping():
            return {"ok": True}

        return app

    def test_allowed_request_passes(self):
        with patch("security.middleware._ipLimiter") as mock_limiter:
            mock_limiter.check.return_value = (True, None)
            app = self._make_app()
            client = TestClient(app, raise_server_exceptions=False)
            res = client.get("/ping")
            assert res.status_code == 200

    def test_blocked_request_returns_429(self):
        with patch("security.middleware._ipLimiter") as mock_limiter:
            mock_limiter.check.return_value = (False, "IP blocked. Try again in 60s")
            app = self._make_app()
            client = TestClient(app, raise_server_exceptions=False)
            res = client.get("/ping")
            assert res.status_code == 429
            assert res.headers.get("Retry-After") == "60"
            body = res.json()
            assert body["errorCode"] == "RATE_LIMIT_EXCEEDED"

    def test_extracts_forwarded_ip(self):
        with patch("security.middleware._ipLimiter") as mock_limiter:
            mock_limiter.check.return_value = (True, None)
            app = self._make_app()
            client = TestClient(app, raise_server_exceptions=False)
            client.get("/ping", headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"})
            called_ip = mock_limiter.check.call_args[0][0]
            assert called_ip == "1.2.3.4"

    def test_uses_direct_ip_when_no_forwarded(self):
        with patch("security.middleware._ipLimiter") as mock_limiter:
            mock_limiter.check.return_value = (True, None)
            app = self._make_app()
            client = TestClient(app, raise_server_exceptions=False)
            client.get("/ping")
            called_ip = mock_limiter.check.call_args[0][0]
            assert called_ip == "testclient"


class TestSecurityHeadersMiddleware:
    def _make_app(self, path="/api"):
        from security.middleware import SecurityHeadersMiddleware
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get(path)
        def endpoint():
            return {"ok": True}

        return app

    def test_security_headers_present(self):
        client = TestClient(self._make_app())
        res = client.get("/api")
        assert res.headers["X-Content-Type-Options"] == "nosniff"
        assert res.headers["X-Frame-Options"] == "DENY"
        assert res.headers["X-XSS-Protection"] == "1; mode=block"
        assert res.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert "max-age=31536000" in res.headers["Strict-Transport-Security"]

    def test_csp_strict_for_normal_paths(self):
        client = TestClient(self._make_app(path="/api"))
        res = client.get("/api")
        csp = res.headers["Content-Security-Policy"]
        assert "script-src 'self'" in csp
        assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]

    def test_csp_relaxed_for_docs(self):
        from security.middleware import SecurityHeadersMiddleware
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/docs")
        def docs():
            return {"ok": True}

        client = TestClient(app)
        res = client.get("/docs")
        csp = res.headers["Content-Security-Policy"]
        assert "unsafe-inline" in csp
