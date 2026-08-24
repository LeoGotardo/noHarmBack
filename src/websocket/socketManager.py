"""WebSocket server using Socket.IO.

Authentication: client must pass JWT access token at connection time via
the `auth` dict → {"token": "<access_token>"} or query string ?token=...

Rooms:
    user_{userId}  — personal room; join on connect
    chat_{chatId}  — chat room; join via `join_chat` event

Events (client → server): see handlers/chatHandlers.py, handlers/presenceHandlers.py
Events (server → client): new_message, messages_read, message_read,
                            typing_indicator, online_status, error
"""

import logging

import socketio
from urllib.parse import parse_qs

# python-socketio only forwards the refusal reason to the client when the
# exception is *its* ConnectionRefusedError. The builtin of the same name is
# caught by a separate branch that replaces the message with a generic
# "Connection refused by server", so the client could never tell an expired
# token (refresh and retry) from a banned account (sign out) — even though it
# already listens for those exact codes on `connect_error`.
from socketio.exceptions import ConnectionRefusedError

from api.dependencies.auth import jwtHandler, getAccountStatus
from core.config import config
from websocket import presence
from websocket.rateLimiter import WsConnectionLimiter

logger = logging.getLogger(__name__)

_REJECTED_STATUSES = {
    config.STATUS_CODES["deleted"],
    config.STATUS_CODES["banned"],
    config.STATUS_CODES["blocked"],
}

def _buildClientManager() -> socketio.AsyncRedisManager | None:
    """Redis pub/sub so a room emit reaches sockets on every instance.

    Without a client manager the room registry is per-process, so
    `sio.emit(room=...)` only ever reached sockets attached to the instance that
    happened to run the emit. The path that broke first was the main one: the
    REST invocation handling POST /messages holds no sockets at all, so the
    recipient was never notified — with two users, not two thousand.

    Falling back to the in-process manager keeps a single-instance deployment
    (the Docker compose stack) working when Redis is unreachable, which is
    exactly the setup where that is still correct.
    """
    try:
        return socketio.AsyncRedisManager(config.REDIS_URL)
    except Exception:
        logger.exception(
            "socket.io could not reach Redis; falling back to the in-process "
            "manager. Room emits will not cross instances."
        )
        return None


sio = socketio.AsyncServer(
    async_mode="asgi",
    client_manager=_buildClientManager(),
    cors_allowed_origins=config.ALLOWED_ORIGINS,
    logger=False,
    engineio_logger=False,
    max_http_buffer_size=2000000,
)

# NOTE: socketio_path is the FULL path (mount prefix included) because the
# BaseHTTPMiddleware stack (RateLimitMiddleware/SecurityHeadersMiddleware)
# prevents Starlette's Mount from stripping the "/ws" prefix — engineio sees
# the un-stripped path, so it must match "/ws/socket.io/". Client connects with
# path "/ws/socket.io".
socketApp = socketio.ASGIApp(sio, socketio_path="ws/socket.io")

_connectionLimiter = WsConnectionLimiter(maxPerUser=3)


# ── Connection lifecycle ───────────────────────────────────────────────────────

@sio.event
async def connect(sid: str, environ: dict, auth: dict | None):
    token = _extractToken(environ, auth)

    if not token:
        raise ConnectionRefusedError("missing_token")

    payload = jwtHandler.verifyToken(token, "access")
    if not payload:
        raise ConnectionRefusedError("invalid_token")

    userId: str = payload["sub"]

    # Same rule as the HTTP dependency — a valid signature is not enough (§1.4).
    status = getAccountStatus(userId)
    if status is None or status in _REJECTED_STATUSES:
        raise ConnectionRefusedError("account_unavailable")

    if not await _connectionLimiter.tryConnect(userId):
        raise ConnectionRefusedError("too_many_connections")

    await sio.save_session(sid, {"userId": userId})
    await presence.add(userId, sid)
    await sio.enter_room(sid, f"user_{userId}")


@sio.event
async def disconnect(sid: str):
    session = await sio.get_session(sid)
    userId: str | None = session.get("userId")
    if userId:
        await _connectionLimiter.onDisconnect(userId)
        await presence.remove(userId, sid)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extractToken(environ: dict, auth: dict | None) -> str | None:
    """Pull token from auth dict first, then query string."""
    if auth and isinstance(auth, dict):
        token = auth.get("token")
        if token:
            return token

    qs = environ.get("QUERY_STRING", "")
    params = parse_qs(qs)
    tokens = params.get("token")
    return tokens[0] if tokens else None


# ── Register handlers ─────────────────────────────────────────────────────────

from websocket.handlers.chatHandlers import register as _registerChat        # noqa: E402
from websocket.handlers.presenceHandlers import register as _registerPresence  # noqa: E402
from websocket.handlers.friendHandlers import register as _registerFriend     # noqa: E402

_registerChat(sio)
_registerPresence(sio)
_registerFriend(sio)
