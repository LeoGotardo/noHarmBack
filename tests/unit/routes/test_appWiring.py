"""Tests against the real application object from src/main.py.

Every other route test builds its own bare FastAPI app and overrides
`getCurrentUser`, so nothing exercised the app that actually ships: main.py sat
at 0% coverage, no test proved that a protected endpoint rejects an anonymous
caller, and the global exception handlers — the thing that turns every raised
error into the shared `{errorCode, message}` envelope — were never invoked.
The 404s asserted elsewhere come from `raise HTTPException` inside the route,
not from a handler.

These are deliberately handler- and wiring-level: they never reach a service,
so no database is involved.
"""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from exceptions.baseExceptions import NoHarmException


@pytest.fixture(scope="module")
def app():
    from main import app as realApp
    return realApp


@pytest.fixture
def client(app):
    # A real peer address, not TestClient's default "testclient": the client-IP
    # resolver only accepts values that parse as addresses, which is what the
    # transport always hands it in production.
    return TestClient(app, raise_server_exceptions=False,
                      client=("203.0.113.7", 12345))


# ── authentication is actually required ───────────────────────────────────────

def _protectedRoutes(app):
    """Every route that declares the getCurrentUser dependency.

    Derived from the app rather than hardcoded, so a new authenticated endpoint
    is covered the moment it is registered — including one that forgets to be.
    """
    from api.dependencies.auth import getCurrentUser

    found = []
    for route in app.routes:
        dependant = getattr(route, "dependant", None)
        if dependant is None:
            continue
        stack = [dependant]
        while stack:
            current = stack.pop()
            if current.call is getCurrentUser:
                found.append((sorted(route.methods - {"HEAD", "OPTIONS"})[0], route.path))
                break
            stack.extend(current.dependencies)
    return sorted(set(found))


# Derived lists have one blind spot: a route that drops getCurrentUser also
# drops out of the list, so the sweep below keeps passing. These are pinned by
# hand and must never stop requiring a token.
_MUST_BE_PROTECTED = [
    ("GET", "/users/me"),
    ("PUT", "/users/me"),
    ("GET", "/users/{userId}"),
    ("GET", "/streaks/current"),
    ("POST", "/streaks/end"),
    ("GET", "/chats"),
    ("GET", "/friendships"),
]


def test_the_app_has_protected_routes(app):
    """Guard for the guard: an empty list would make the sweep vacuous."""
    assert len(_protectedRoutes(app)) > 5


@pytest.mark.parametrize("method, path", _MUST_BE_PROTECTED)
def test_named_route_still_declares_authentication(app, method, path):
    known = {(m, p) for m, p in _protectedRoutes(app)}
    registered = {(m, getattr(r, "path", "")) for r in app.routes
                  for m in (getattr(r, "methods", None) or set())}
    assert (method, path) in registered, f"{method} {path} is no longer registered"
    assert (method, path) in known, f"{method} {path} no longer requires a token"


def test_protected_routes_reject_anonymous_callers(app, client):
    """No Authorization header must never reach a handler."""
    leaked = []
    for method, path in _protectedRoutes(app):
        url = path.replace("{userId}", "someone").replace("{chatId}", "c") \
                  .replace("{messageId}", "m").replace("{friendshipId}", "f") \
                  .replace("{badgeId}", "b").replace("{streakId}", "s") \
                  .replace("{userBadgeId}", "ub").replace("{notificationId}", "n")
        res = client.request(method, url, json={})
        if res.status_code not in (401, 403):
            leaked.append((method, url, res.status_code))
    assert leaked == []


def test_protected_route_rejects_a_malformed_token(client):
    res = client.get("/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


def test_protected_route_rejects_a_non_bearer_scheme(client):
    res = client.get("/users/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
    assert res.status_code in (401, 403)


def test_public_routes_stay_reachable(client):
    assert client.get("/health").status_code == 200
    assert client.get("/openapi.json").status_code == 200


# ── global exception handlers ─────────────────────────────────────────────────

@pytest.fixture(scope="module")
def probe(app):
    """Endpoints that raise on demand, registered once on the real app."""

    @app.get("/__probe/noharm")
    def _noharm(code: int = 404):
        raise NoHarmException(statusCode=code, errorCode="PROBE", message="probe failed", details={"k": "v"})

    @app.get("/__probe/http")
    def _http():
        raise HTTPException(status_code=409, detail="already exists")

    @app.get("/__probe/boom")
    def _boom():
        raise RuntimeError("unexpected")

    yield
    app.router.routes = [r for r in app.router.routes
                         if not getattr(r, "path", "").startswith("/__probe")]


def test_noHarmException_becomes_the_shared_envelope(client, probe):
    res = client.get("/__probe/noharm", params={"code": 404})
    assert res.status_code == 404
    body = res.json()
    assert body["errorCode"] == "PROBE"
    assert body["message"] == "probe failed"
    assert body["details"] == {"k": "v"}


def test_httpException_detail_is_normalised_into_the_envelope(client, probe):
    """Routes raise HTTPException; clients must still see {errorCode, message}."""
    res = client.get("/__probe/http")
    assert res.status_code == 409
    body = res.json()
    assert body["message"] == "already exists"
    assert body["errorCode"] == "CONFLICT"
    assert "detail" not in body


def test_unhandled_exception_becomes_500_in_the_envelope(client, probe):
    res = client.get("/__probe/boom")
    assert res.status_code == 500
    assert res.json()["errorCode"] == "INTERNAL_ERROR"


def test_validation_error_returns_422_envelope(client):
    res = client.post("/auth/login", json={"uid": "only-uid"})  # email missing
    assert res.status_code == 422
    body = res.json()
    assert body["errorCode"] == "VALIDATION_ERROR"
    assert isinstance(body["details"], list)


def test_unknown_path_returns_404_envelope(client):
    res = client.get("/no-such-endpoint")
    assert res.status_code == 404
    assert res.json()["errorCode"] == "NOT_FOUND"


def test_error_responses_carry_cors_headers_for_allowed_origins(client, probe):
    """A 4xx without CORS headers reaches the browser as an opaque network
    error, so the client cannot show the real message."""
    origin = "http://localhost:3000"
    res = client.get("/__probe/noharm", headers={"Origin": origin})
    assert res.headers.get("Access-Control-Allow-Origin") == origin


def test_error_responses_omit_cors_headers_for_foreign_origins(client, probe):
    res = client.get("/__probe/noharm", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in res.headers


# ── middleware is actually wired in ───────────────────────────────────────────

def test_security_headers_are_applied_on_the_real_app(client):
    res = client.get("/health")
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["X-Frame-Options"] == "DENY"
    assert "max-age=31536000" in res.headers["Strict-Transport-Security"]
    assert "frame-ancestors 'none'" in res.headers["Content-Security-Policy"]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known gap: SecurityHeadersMiddleware re-raises unhandled exceptions so "
        "ServerErrorMiddleware can build the response through the app handler. "
        "That response is assembled outside this middleware, so 500s ship with "
        "no nosniff / X-Frame-Options / CSP. Delete the xfail when fixed."
    ),
)
def test_security_headers_are_applied_to_error_responses(client, probe):
    res = client.get("/__probe/boom")
    assert res.headers["X-Content-Type-Options"] == "nosniff"


class _CountingIpLimiter:
    """Stand-in for the middleware's IpRateLimiter.

    A real (or fake) async Redis client cannot be used here: TestClient spins up
    a fresh event loop per request, and an aioredis connection created on one
    loop raises on the next — which the limiter catches as "store is down" and
    fails open, so nothing would ever be blocked. Counting in plain Python keeps
    the middleware itself as the thing under test.
    """

    def __init__(self, maxRequests):
        self.maxRequests = maxRequests
        self.seen = []

    async def check(self, ip):
        self.seen.append(ip)
        if len(self.seen) > self.maxRequests:
            return False, "IP blocked. Try again in 60s", 60
        return True, None, 0


def test_per_route_ceiling_returns_429_through_the_real_app(app, client):
    """The slowapi decorator raises RateLimitExceeded; main.py must own a
    handler for it, otherwise the ceiling surfaces as a 500."""
    from fastapi import Request
    from security.limiter import limiter

    @app.get("/__probe/limited")
    @limiter.limit("3/minute")
    def _limited(request: Request):
        return {"ok": True}

    try:
        codes = [client.get("/__probe/limited").status_code for _ in range(5)]
    finally:
        app.router.routes = [r for r in app.router.routes
                             if getattr(r, "path", "") != "/__probe/limited"]

    assert codes[:3] == [200, 200, 200]
    assert codes[3:] == [429, 429]


def _trip_per_route_limit(app, client, path):
    from fastapi import Request
    from security.limiter import limiter

    @app.get(path)
    @limiter.limit("1/minute")
    def _probe(request: Request):
        return {"ok": True}

    try:
        client.get(path)
        return client.get(path)
    finally:
        app.router.routes = [r for r in app.router.routes
                             if getattr(r, "path", "") != path]


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known gap: slowapi's _rate_limit_exceeded_handler only injects "
        "Retry-After when the Limiter is built with headers_enabled=True, and "
        "security/limiter.py does not. The global middleware sends it, the "
        "per-route ceilings do not, so a client hitting the tighter limit has "
        "nothing to back off on. Delete the xfail when limiter.py sets it."
    ),
)
def test_per_route_ceiling_sends_retry_after(app, client):
    res = _trip_per_route_limit(app, client, "/__probe/retry")
    assert res.status_code == 429
    assert int(res.headers["Retry-After"]) > 0


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known gap: the per-route 429 body is slowapi's own "
        "{'error': 'Rate limit exceeded: ...'}, not the {errorCode, message} "
        "envelope every other error in this API uses — including the 429 from "
        "RateLimitMiddleware. Clients need two parsers for the same status. "
        "Delete the xfail once main.py registers an envelope-shaped handler."
    ),
)
def test_per_route_ceiling_uses_the_shared_error_envelope(app, client):
    res = _trip_per_route_limit(app, client, "/__probe/envelope")
    assert res.json()["errorCode"] == "RATE_LIMIT_EXCEEDED"


def test_global_ip_middleware_returns_429_on_the_real_app(client):
    """The floor that does run before routing, auth and validation."""
    from unittest.mock import patch

    tight = _CountingIpLimiter(maxRequests=3)
    with patch("security.middleware._ipLimiter", tight):
        codes = [client.get("/users/me").status_code for _ in range(6)]

    assert codes[0] == 401   # unauthenticated, but not yet limited
    assert codes[-1] == 429


def test_ip_middleware_runs_before_authentication(client):
    """Anonymous traffic must be throttled too, or the 401 path is a free ride."""
    from unittest.mock import patch

    tight = _CountingIpLimiter(maxRequests=100)
    with patch("security.middleware._ipLimiter", tight):
        client.get("/users/me")

    assert tight.seen == ["203.0.113.7"]


def test_health_stays_reachable_while_the_ip_bucket_is_blocked(client):
    """A blocked bucket must not make an orchestrator recycle a healthy box."""
    from unittest.mock import patch

    tight = _CountingIpLimiter(maxRequests=1)
    with patch("security.middleware._ipLimiter", tight):
        client.get("/users/me")
        assert client.get("/users/me").status_code == 429
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200


def test_root_redirects_to_docs(client):
    res = client.get("/", follow_redirects=False)
    assert res.status_code in (307, 302)
    assert res.headers["location"] == "/docs"
