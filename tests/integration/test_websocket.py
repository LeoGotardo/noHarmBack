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


class TestConnectionLimiter:
    """WsConnectionLimiter exercised against real Redis."""

    @pytest.fixture
    def uid(self):
        return str(uuid.uuid4())

    async def test_up_to_limit_allowed(self, uid):
        from websocket.rateLimiter import WsConnectionLimiter
        lim = WsConnectionLimiter(maxPerUser=3)
        for _ in range(3):
            assert await lim.tryConnect(uid) is True

    async def test_over_limit_refused(self, uid):
        from websocket.rateLimiter import WsConnectionLimiter
        lim = WsConnectionLimiter(maxPerUser=3)
        for _ in range(3):
            await lim.tryConnect(uid)
        assert await lim.tryConnect(uid) is False

    async def test_refused_does_not_increment_counter(self, uid):
        from websocket.rateLimiter import WsConnectionLimiter, _redis
        lim = WsConnectionLimiter(maxPerUser=3)
        for _ in range(3):
            await lim.tryConnect(uid)
        await lim.tryConnect(uid)  # refused — decr rolls back
        count = int(await _redis.get(f"ws:conn:{uid}") or 0)
        assert count == 3

    async def test_disconnect_decrements_allowing_reconnect(self, uid):
        from websocket.rateLimiter import WsConnectionLimiter
        lim = WsConnectionLimiter(maxPerUser=3)
        for _ in range(3):
            await lim.tryConnect(uid)
        await lim.onDisconnect(uid)
        assert await lim.tryConnect(uid) is True

    async def test_disconnect_when_no_connection_does_not_go_negative(self, uid):
        from websocket.rateLimiter import WsConnectionLimiter, _redis
        lim = WsConnectionLimiter(maxPerUser=3)
        await lim.onDisconnect(uid)  # no prior connect
        count = int(await _redis.get(f"ws:conn:{uid}") or 0)
        assert count >= 0

    async def test_different_users_have_independent_counters(self):
        from websocket.rateLimiter import WsConnectionLimiter
        lim = WsConnectionLimiter(maxPerUser=3)
        uid_a = str(uuid.uuid4())
        uid_b = str(uuid.uuid4())
        for _ in range(3):
            await lim.tryConnect(uid_a)
        # uid_a is at limit; uid_b should still connect
        assert await lim.tryConnect(uid_b) is True
