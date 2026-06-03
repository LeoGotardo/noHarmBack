"""
Security / middleware integration tests.

Rate-limit tests work by resetting the in-memory limiter between tests
(done in conftest autouse fixture) and then making N+1 requests with a
fixed IP header to trigger the 429 from RateLimitMiddleware.
"""

import pytest

_SECURITY_HEADERS = [
    "X-Content-Type-Options",
    "X-Frame-Options",
    "X-XSS-Protection",
    "Strict-Transport-Security",
    "Content-Security-Policy",
]


class TestSecurityHeaders:
    def test_security_headers_present_on_200(self, client, user_a):
        resp = client.get("/users/me", headers=user_a["headers"])
        for h in _SECURITY_HEADERS:
            assert h in resp.headers, f"Missing header: {h}"

    def test_security_headers_present_on_401(self, client):
        resp = client.get("/users/me")
        for h in _SECURITY_HEADERS:
            assert h in resp.headers, f"Missing header: {h}"

    def test_docs_csp_allows_cdn(self, client):
        resp = client.get("/docs")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "cdn.jsdelivr.net" in csp

    def test_api_csp_does_not_allow_cdn(self, client):
        resp = client.get("/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        assert "cdn.jsdelivr.net" not in csp


class TestAuth:
    def test_missing_token_returns_401(self, client):
        for path in ["/users/me", "/streaks/current", "/chats"]:
            resp = client.get(path)
            assert resp.status_code == 401, f"Expected 401 for {path}"

    def test_invalid_bearer_token_returns_401(self, client):
        resp = client.get("/users/me", headers={"Authorization": "Bearer not.a.real.token"})
        assert resp.status_code == 401

    def test_expired_or_tampered_token_returns_401(self, client, user_a):
        bad = user_a["access"] + "corrupted"
        resp = client.get("/users/me", headers={"Authorization": f"Bearer {bad}"})
        assert resp.status_code == 401


class TestGlobalRateLimit:
    def test_ip_rate_limit_returns_429(self, client):
        """After 60 requests from the same IP, the 61st gets 429."""
        from security.middleware import _ipLimiter

        # Seed the window with 60 requests (one below the limit)
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc)
        _ipLimiter._windows["testclient"] = [ts] * 60

        resp = client.get("/health", headers={"X-Forwarded-For": "testclient"})
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
