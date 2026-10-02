"""
WebSocket integration tests.

Tests JWT authentication (as used by the connect handler) and the
WsConnectionLimiter with real Redis. No network server is started —
components are exercised directly so these tests run without a live
socket server.
"""

import uuid
import pytest


class TestJwtAuth:
    """JWT validation path that the connect handler runs through."""

    def test_valid_access_token_is_verified(self, jwt_factory):
        uid = str(uuid.uuid4())
        token = jwt_factory.createAccessToken(uid)
        payload = jwt_factory.verifyToken(token, "access")
        assert payload is not None
        assert payload["sub"] == uid

    def test_tampered_token_returns_none(self, jwt_factory):
        uid = str(uuid.uuid4())
        token = jwt_factory.createAccessToken(uid) + "tampered"
        assert jwt_factory.verifyToken(token, "access") is None

    def test_garbage_string_returns_none(self, jwt_factory):
        assert jwt_factory.verifyToken("not.a.real.token", "access") is None

    def test_blacklisted_token_returns_none(self, jwt_factory):
        uid = str(uuid.uuid4())
        token = jwt_factory.createAccessToken(uid)
        payload = jwt_factory.verifyToken(token, "access")
        from datetime import datetime, timezone, timedelta
        exp = datetime.now(timezone.utc) + timedelta(minutes=15)
        jwt_factory._blacklist.add(payload["jti"], exp)
        assert jwt_factory.verifyToken(token, "access") is None

    def test_refresh_token_rejected_for_access_slot(self, jwt_factory):
        uid = str(uuid.uuid4())
        refresh = jwt_factory.createRefreshToken(uid)
        assert jwt_factory.verifyToken(refresh, "access") is None


@pytest.mark.asyncio(loop_scope="module")
class TestConnectionLimiter:
    """WsConnectionLimiter exercised against real Redis.

    Pinned to one event loop for the whole module. `websocket/rateLimiter.py`
    builds its `redis.asyncio` client once, at import, and that client binds its
    connection pool to the first loop that uses it — which is correct in
    production, where the process has exactly one loop for its lifetime. Under
    pytest-asyncio's default of a fresh loop per test, the first two tests here
    passed and every later one died with `got Future attached to a different
    loop`, then `Event loop is closed`. Nothing was wrong with the limiter; the
    harness was handing a process-lifetime object a new loop each time.
    """

    @pytest.fixture
    def uid(self):
        return str(uuid.uuid4())

    async def test_up_to_the_cap_nothing_is_evicted(self, uid):
        from websocket.rateLimiter import WsConnectionLimiter
        lim = WsConnectionLimiter(maxPerUser=3)
        for n in range(3):
            assert await lim.admit(uid, f"sid-{n}") == []

    async def test_past_the_cap_the_oldest_goes(self, uid):
        from websocket.rateLimiter import WsConnectionLimiter
        lim = WsConnectionLimiter(maxPerUser=3)
        for n in range(3):
            await lim.admit(uid, f"sid-{n}")
        assert await lim.admit(uid, "sid-3") == ["sid-0"]
        assert await lim.admit(uid, "sid-4") == ["sid-1"]

    async def test_the_set_never_exceeds_the_cap(self, uid):
        from websocket.rateLimiter import WsConnectionLimiter, _redis
        lim = WsConnectionLimiter(maxPerUser=3)
        for n in range(6):
            await lim.admit(uid, f"sid-{n}")
        assert await _redis.zcard(f"ws:conns:{uid}") == 3

    async def test_a_disconnect_frees_a_slot(self, uid):
        from websocket.rateLimiter import WsConnectionLimiter
        lim = WsConnectionLimiter(maxPerUser=3)
        for n in range(3):
            await lim.admit(uid, f"sid-{n}")
        await lim.onDisconnect(uid, "sid-1")
        assert await lim.admit(uid, "sid-3") == []

    async def test_a_stale_entry_heals_itself(self, uid):
        """A worker that died without a disconnect leaves an entry behind; it
        is just the oldest, and the next connection over the cap removes it."""
        from websocket.rateLimiter import WsConnectionLimiter
        lim = WsConnectionLimiter(maxPerUser=1)
        await lim.admit(uid, "sid-from-a-dead-worker")
        assert await lim.admit(uid, "sid-live") == ["sid-from-a-dead-worker"]

    async def test_users_are_independent(self):
        from websocket.rateLimiter import WsConnectionLimiter
        lim = WsConnectionLimiter(maxPerUser=1)
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        await lim.admit(a, "sid-a")
        assert await lim.admit(b, "sid-b") == []
