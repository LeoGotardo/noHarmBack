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

import socketio
from urllib.parse import parse_qs

from api.dependencies.auth import jwtHandler
from core.config import config

# userId → sid — in-memory presence map (single-process)
connectedUsers: dict[str, str] = {}

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=config.ALLOWED_ORIGINS,
    logger=False,
    engineio_logger=False,
)

socketApp = socketio.ASGIApp(sio, socketio_path="socket.io")


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
    await sio.save_session(sid, {"userId": userId})
    connectedUsers[userId] = sid
    sio.enter_room(sid, f"user_{userId}")


@sio.event
async def disconnect(sid: str):
    session = await sio.get_session(sid)
    userId: str | None = session.get("userId")
    if userId and connectedUsers.get(userId) == sid:
        del connectedUsers[userId]


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

_registerChat(sio, connectedUsers)
_registerPresence(sio, connectedUsers)
