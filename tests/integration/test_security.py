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
        """One request past the ceiling gets 429, with Retry-After.

        The ceiling is lowered instead of the window being pre-filled. This
        test used to seed `_ipLimiter._windows`, an in-process dict that
        stopped existing when the limiter moved to a Redis sorted set — so it
        failed with AttributeError before reaching a single assertion, and had
        been testing nothing since. Driving real requests through the real
        middleware is also the only version that would notice the Lua script
        breaking.

        It also has to stop asking `/health`, which is in the middleware's
        `_EXEMPT_PATHS` — an orchestrator that gets a 429 from a health check
        restarts the container. `/users/me` with no token is a request the
        limiter actually counts; the 401 it returns is proof the middleware ran
        and let it through, which is the state the last one has to change.
        """
        from security.middleware import _ipLimiter

        original = _ipLimiter._maxRequests
        _ipLimiter._maxRequests = 3
        try:
            for _ in range(3):
                assert client.get("/users/me").status_code == 401

            resp = client.get("/users/me")
        finally:
            _ipLimiter._maxRequests = original

        assert resp.status_code == 429
        assert "Retry-After" in resp.headers
