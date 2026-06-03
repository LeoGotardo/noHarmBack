import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Module-level autouse fixtures (active for every test) ─────────────────────

@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.get = AsyncMock(return_value=None)
    r.incr = AsyncMock(return_value=1)
    r.decr = AsyncMock(return_value=0)
    r.expire = AsyncMock(return_value=True)
    return r


@pytest.fixture
def mock_sio():
    sio = AsyncMock()
    sio.get_session = AsyncMock(return_value={"userId": "user-abc"})
    sio.emit = AsyncMock()
    return sio


@pytest.fixture(autouse=True)
def patch_ws_redis(mock_redis):
    """Replace module-level _redis with the mock for every test."""
    with patch("websocket.rateLimiter._redis", mock_redis):
        yield


@pytest.fixture(autouse=True)
def patch_socketmanager(mock_sio):
    """Inject fake websocket.socketManager so wsLimit's lazy import resolves."""
    fake_module = MagicMock()
    fake_module.sio = mock_sio
    with patch.dict(sys.modules, {"websocket.socketManager": fake_module}):
        yield


# ── WsConnectionLimiter ───────────────────────────────────────────────────────

class TestWsConnectionLimiter:

    @pytest.fixture
    def limiter(self):
        from websocket.rateLimiter import WsConnectionLimiter
        return WsConnectionLimiter(maxPerUser=3)

    async def test_tryConnect_returns_true_when_under_limit(self, limiter, mock_redis):
        mock_redis.incr.return_value = 1
        assert await limiter.tryConnect("user-1") is True

    async def test_tryConnect_returns_true_at_exact_limit(self, limiter, mock_redis):
        mock_redis.incr.return_value = 3
        assert await limiter.tryConnect("user-1") is True

    async def test_tryConnect_returns_false_when_over_limit(self, limiter, mock_redis):
        mock_redis.incr.return_value = 4
        assert await limiter.tryConnect("user-1") is False

    async def test_tryConnect_rollbacks_decr_when_over_limit(self, limiter, mock_redis):
        mock_redis.incr.return_value = 4
        await limiter.tryConnect("user-1")
        mock_redis.decr.assert_called_once_with("ws:conn:user-1")

    async def test_tryConnect_no_decr_when_under_limit(self, limiter, mock_redis):
        mock_redis.incr.return_value = 2
        await limiter.tryConnect("user-1")
        mock_redis.decr.assert_not_called()

    async def test_tryConnect_sets_expiry_on_key(self, limiter, mock_redis):
        mock_redis.incr.return_value = 1
        await limiter.tryConnect("user-1")
        mock_redis.expire.assert_called_once_with("ws:conn:user-1", 86400)

    async def test_tryConnect_uses_correct_key_prefix(self, limiter, mock_redis):
        mock_redis.incr.return_value = 1
        await limiter.tryConnect("abc-123")
        mock_redis.incr.assert_called_once_with("ws:conn:abc-123")

    async def test_onDisconnect_decrements_when_count_positive(self, limiter, mock_redis):
        mock_redis.get.return_value = "2"
        await limiter.onDisconnect("user-1")
        mock_redis.decr.assert_called_once_with("ws:conn:user-1")

    async def test_onDisconnect_skips_decr_when_count_zero(self, limiter, mock_redis):
        mock_redis.get.return_value = "0"
        await limiter.onDisconnect("user-1")
        mock_redis.decr.assert_not_called()

    async def test_onDisconnect_skips_decr_when_key_missing(self, limiter, mock_redis):
        mock_redis.get.return_value = None
        await limiter.onDisconnect("user-1")
        mock_redis.decr.assert_not_called()

    async def test_different_users_use_different_keys(self, limiter, mock_redis):
        mock_redis.incr.return_value = 1
        await limiter.tryConnect("user-A")
        await limiter.tryConnect("user-B")
        keys = [call.args[0] for call in mock_redis.incr.call_args_list]
        assert "ws:conn:user-A" in keys
        assert "ws:conn:user-B" in keys
        assert keys[0] != keys[1]

    async def test_custom_max_per_user_respected(self, mock_redis):
        from websocket.rateLimiter import WsConnectionLimiter
        limiter = WsConnectionLimiter(maxPerUser=1)
        mock_redis.incr.return_value = 2
        assert await limiter.tryConnect("user-1") is False

    async def test_max_per_user_default_is_three(self):
        from websocket.rateLimiter import WsConnectionLimiter
        assert WsConnectionLimiter().maxPerUser == 3


# ── wsLimit decorator ─────────────────────────────────────────────────────────

class TestWsLimit:

    @pytest.fixture
    def make_handler(self):
        def _make(maxCalls: int = 5, windowSeconds: int = 60):
            from websocket.rateLimiter import wsLimit
            inner = AsyncMock(return_value="ok")
            inner.__name__ = "testHandler"
            return wsLimit(maxCalls=maxCalls, windowSeconds=windowSeconds)(inner), inner
        return _make

    async def test_calls_handler_when_under_limit(self, make_handler, mock_redis):
        mock_redis.incr.return_value = 1
        decorated, inner = make_handler(maxCalls=5)
        await decorated("sid-1", {"data": 1})
        inner.assert_called_once_with("sid-1", {"data": 1})

    async def test_returns_handler_value_when_under_limit(self, make_handler, mock_redis):
        mock_redis.incr.return_value = 3
        decorated, _ = make_handler(maxCalls=5)
        assert await decorated("sid-1") == "ok"

    async def test_emits_ws_error_when_over_limit(self, make_handler, mock_redis, mock_sio):
        mock_redis.incr.return_value = 6
        decorated, _ = make_handler(maxCalls=5)
        await decorated("sid-1")
        mock_sio.emit.assert_called_once()
        event, payload = mock_sio.emit.call_args[0]
        assert event == "ws_error"
        assert payload["code"] == "RATE_LIMITED"

    async def test_does_not_call_handler_when_over_limit(self, make_handler, mock_redis):
        mock_redis.incr.return_value = 6
        decorated, inner = make_handler(maxCalls=5)
        await decorated("sid-1")
        inner.assert_not_called()

    async def test_returns_none_when_over_limit(self, make_handler, mock_redis):
        mock_redis.incr.return_value = 6
        decorated, _ = make_handler(maxCalls=5)
        assert await decorated("sid-1") is None

    async def test_calls_handler_at_exact_limit(self, make_handler, mock_redis):
        mock_redis.incr.return_value = 5
        decorated, inner = make_handler(maxCalls=5)
        await decorated("sid-1")
        inner.assert_called_once()

    async def test_sets_ttl_on_first_call(self, make_handler, mock_redis):
        mock_redis.incr.return_value = 1
        decorated, _ = make_handler(maxCalls=5, windowSeconds=30)
        await decorated("sid-1")
        mock_redis.expire.assert_called_once()
        _, ttl = mock_redis.expire.call_args[0]
        assert ttl == 30

    async def test_does_not_reset_ttl_after_first_call(self, make_handler, mock_redis):
        mock_redis.incr.return_value = 2
        decorated, _ = make_handler(maxCalls=5, windowSeconds=30)
        await decorated("sid-1")
        mock_redis.expire.assert_not_called()

    async def test_rate_key_includes_user_id(self, make_handler, mock_redis, mock_sio):
        mock_redis.incr.return_value = 1
        mock_sio.get_session.return_value = {"userId": "user-xyz"}
        decorated, _ = make_handler(maxCalls=5)
        await decorated("sid-1")
        key = mock_redis.incr.call_args[0][0]
        assert "user-xyz" in key

    async def test_rate_key_includes_handler_name(self, make_handler, mock_redis):
        mock_redis.incr.return_value = 1
        decorated, _ = make_handler(maxCalls=5)
        await decorated("sid-1")
        key = mock_redis.incr.call_args[0][0]
        assert "testHandler" in key

    async def test_different_handlers_use_different_keys(self, mock_redis, mock_sio):
        mock_redis.incr.return_value = 1
        from websocket.rateLimiter import wsLimit

        handlerA = AsyncMock(return_value=None)
        handlerA.__name__ = "handlerA"
        handlerB = AsyncMock(return_value=None)
        handlerB.__name__ = "handlerB"

        await wsLimit(maxCalls=5, windowSeconds=60)(handlerA)("sid-1")
        await wsLimit(maxCalls=5, windowSeconds=60)(handlerB)("sid-1")

        keys = [call.args[0] for call in mock_redis.incr.call_args_list]
        assert keys[0] != keys[1]

    async def test_falls_back_to_sid_when_no_user_id_in_session(self, make_handler, mock_redis, mock_sio):
        mock_redis.incr.return_value = 1
        mock_sio.get_session.return_value = {}
        decorated, _ = make_handler(maxCalls=5)
        await decorated("sid-fallback")
        key = mock_redis.incr.call_args[0][0]
        assert "sid-fallback" in key

    async def test_ws_error_emitted_to_correct_sid(self, make_handler, mock_redis, mock_sio):
        mock_redis.incr.return_value = 99
        decorated, _ = make_handler(maxCalls=5)
        await decorated("my-sid")
        kwargs = mock_sio.emit.call_args[1]
        assert kwargs.get("to") == "my-sid"

    async def test_preserves_handler_name(self):
        from websocket.rateLimiter import wsLimit

        async def myCustomHandler(sid, data): ...
        decorated = wsLimit(maxCalls=5, windowSeconds=60)(myCustomHandler)
        assert decorated.__name__ == "myCustomHandler"
