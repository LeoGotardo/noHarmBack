"""Unit tests for the Socket.IO server wiring.

The client manager is the single line that decides whether real-time delivery
works on more than one instance, and nothing covered it: removing
`client_manager=...` from the AsyncServer left the whole suite green while
breaking message delivery for every user not sharing an instance with the
sender.
"""

import socketio
from unittest.mock import patch


def _module():
    import websocket.socketManager as module
    return module


# ── client manager ────────────────────────────────────────────────────────────

def test_the_server_uses_a_redis_backed_manager():
    """Without it, `sio.emit(room=...)` only reaches sockets on the instance
    that ran the emit — and the REST invocation that persists a message holds
    no sockets at all."""
    assert isinstance(_module().sio.manager, socketio.AsyncRedisManager)


def test_the_manager_points_at_the_configured_redis():
    from core.config import config
    manager = _module()._buildClientManager()
    assert isinstance(manager, socketio.AsyncRedisManager)
    assert manager.redis_url == config.REDIS_URL


def test_manager_falls_back_in_process_when_redis_is_unavailable():
    """A single-instance deployment (the Docker compose stack) is still correct
    with the in-process manager, so an unreachable Redis must not stop the app
    from booting."""
    module = _module()
    with patch.object(socketio, "AsyncRedisManager", side_effect=ConnectionError("redis is down")):
        assert module._buildClientManager() is None


def test_fallback_is_logged_loudly(caplog):
    module = _module()
    with patch.object(socketio, "AsyncRedisManager", side_effect=ConnectionError("redis is down")):
        module._buildClientManager()
    assert "Room emits will not cross instances" in caplog.text


# ── server options that the client depends on ─────────────────────────────────

def test_socketio_path_matches_the_client_path():
    """The mount prefix is baked into socketio_path because the middleware
    stack stops Starlette's Mount from stripping it, so engineio sees the
    un-stripped path. The client sets `path: "/ws/socket.io"`, and any relay
    put in front has to forward to this exact path.
    """
    assert _module().socketApp.engineio_path == "/ws/socket.io/"


def test_buffer_is_large_enough_for_the_proxy_payload_ceiling():
    """A relay in front of this server caps frames at 256 KB by default; the
    server must not be the tighter of the two or large frames die mid-path."""
    assert _module().sio.eio.max_http_buffer_size >= 256 * 1024


def test_rejected_account_states_match_the_http_dependency():
    """A banned account must not keep a socket open just because the socket
    path re-implements the check (§1.4)."""
    from core.config import config
    assert _module()._REJECTED_STATUSES == {
        config.STATUS_CODES["deleted"],
        config.STATUS_CODES["banned"],
        config.STATUS_CODES["blocked"],
    }


# ── connection lifecycle ──────────────────────────────────────────────────────
#
# The socket path re-implements the HTTP dependency's checks by hand — token,
# then account state, then the per-user connection cap. None of it was covered,
# so dropping the §1.4 account check left the suite green while letting a banned
# user hold an open socket.

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from socketio.exceptions import ConnectionRefusedError

from core.config import config


def _handler(name):
    return _module().sio.handlers["/"][name]


@pytest.fixture
def wiring():
    """Patch everything `connect` reaches out to, defaulting to the happy path."""
    module = _module()
    limiter = MagicMock()
    limiter.tryConnect = AsyncMock(return_value=True)
    limiter.onDisconnect = AsyncMock()

    presence = MagicMock()
    presence.add = AsyncMock()
    presence.remove = AsyncMock()

    with patch.object(module, "jwtHandler") as jwt, \
         patch.object(module, "getAccountStatus", return_value=config.STATUS_CODES["enabled"]) as status, \
         patch.object(module, "_connectionLimiter", limiter), \
         patch.object(module, "presence", presence), \
         patch.object(module.sio, "save_session", AsyncMock()), \
         patch.object(module.sio, "enter_room", AsyncMock()) as enterRoom, \
         patch.object(module.sio, "get_session", AsyncMock(return_value={"userId": "uid-1"})):
        jwt.verifyToken.return_value = {"sub": "uid-1"}
        yield MagicMock(jwt=jwt, status=status, limiter=limiter,
                        presence=presence, enterRoom=enterRoom, module=module)


async def test_connect_accepts_a_valid_token(wiring):
    await _handler("connect")("sid-1", {}, {"token": "good"})

    wiring.jwt.verifyToken.assert_called_once_with("good", "access")
    wiring.presence.add.assert_awaited_once_with("uid-1", "sid-1")


async def test_connect_joins_the_personal_room(wiring):
    """Chat events are delivered to `user_{id}` only, so a socket that never
    joins it receives nothing."""
    await _handler("connect")("sid-1", {}, {"token": "good"})

    wiring.enterRoom.assert_awaited_once_with("sid-1", "user_uid-1")


async def test_refusals_use_the_socketio_exception_not_the_builtin(wiring):
    """python-socketio forwards `error_args` only for its own exception class.
    Raising the builtin ConnectionRefusedError makes the server replace every
    reason with "Connection refused by server", and the client can no longer
    tell an expired token from a banned account."""
    module = _module()
    assert module.ConnectionRefusedError is ConnectionRefusedError
    assert ConnectionRefusedError("missing_token").error_args == {"message": "missing_token"}


async def test_connect_without_a_token_is_refused(wiring):
    with pytest.raises(ConnectionRefusedError, match="missing_token"):
        await _handler("connect")("sid-1", {"QUERY_STRING": ""}, None)


async def test_connect_reads_the_token_from_the_query_string(wiring):
    await _handler("connect")("sid-1", {"QUERY_STRING": "token=fromqs"}, None)

    wiring.jwt.verifyToken.assert_called_once_with("fromqs", "access")


async def test_connect_with_an_invalid_token_is_refused(wiring):
    wiring.jwt.verifyToken.return_value = None
    with pytest.raises(ConnectionRefusedError, match="invalid_token"):
        await _handler("connect")("sid-1", {}, {"token": "bad"})


@pytest.mark.parametrize("state", ["deleted", "banned", "blocked"])
async def test_connect_refuses_a_dead_account(wiring, state):
    """§1.4 — a valid signature is not enough on the socket path either."""
    with patch.object(wiring.module, "getAccountStatus", return_value=config.STATUS_CODES[state]):
        with pytest.raises(ConnectionRefusedError, match="account_unavailable"):
            await _handler("connect")("sid-1", {}, {"token": "good"})


async def test_connect_refuses_when_the_user_row_is_gone(wiring):
    with patch.object(wiring.module, "getAccountStatus", return_value=None):
        with pytest.raises(ConnectionRefusedError, match="account_unavailable"):
            await _handler("connect")("sid-1", {}, {"token": "good"})


async def test_connect_refuses_over_the_connection_cap(wiring):
    wiring.limiter.tryConnect.return_value = False
    with pytest.raises(ConnectionRefusedError, match="too_many_connections"):
        await _handler("connect")("sid-1", {}, {"token": "good"})


async def test_a_refused_connection_records_no_presence(wiring):
    wiring.limiter.tryConnect.return_value = False
    with pytest.raises(ConnectionRefusedError):
        await _handler("connect")("sid-1", {}, {"token": "good"})

    wiring.presence.add.assert_not_awaited()


async def test_disconnect_releases_presence_and_the_cap(wiring):
    await _handler("disconnect")("sid-1")

    wiring.presence.remove.assert_awaited_once_with("uid-1", "sid-1")
    wiring.limiter.onDisconnect.assert_awaited_once_with("uid-1")


async def test_disconnect_without_a_session_user_is_a_no_op(wiring):
    with patch.object(wiring.module.sio, "get_session", AsyncMock(return_value={})):
        await _handler("disconnect")("sid-1")

    wiring.presence.remove.assert_not_awaited()
    wiring.limiter.onDisconnect.assert_not_awaited()
