"""Server → client Socket.IO emission, callable from sync and async code.

REST handlers run in Starlette's threadpool (no running event loop), while the
Socket.IO handlers run inside the loop. Both need to publish the same events, so
every emit goes through `emit()`, which schedules the coroutine on the loop bound
at application startup (`bindLoop`).

Payloads are converted to JSON-safe primitives first — engineio serialises with
`json.dumps`, which raises on UUID/datetime and silently drops the event.
"""

import asyncio
import dataclasses
import logging

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_loop: Optional[asyncio.AbstractEventLoop] = None

# Ceiling for `toJsonSafe` recursion. Event payloads are shallow; anything deeper
# is a cycle or an object whose duck-typed `model_dump` keeps handing back new
# objects (a MagicMock does exactly that, and will happily exhaust the machine).
_MAX_DEPTH = 8


def bindLoop(loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """Remember the loop that Socket.IO runs on. Called once at app startup."""
    global _loop
    _loop = loop or asyncio.get_running_loop()


# ── serialisation ─────────────────────────────────────────────────────────────

def toJsonSafe(value: Any, _depth: int = 0) -> Any:
    """Recursively convert ORM rows/dataclasses/UUID/datetime/Decimal into JSON primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if _depth >= _MAX_DEPTH:
        return str(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return toJsonSafe(dataclasses.asdict(value), _depth + 1)
    if isinstance(value, dict):
        return {str(k): toJsonSafe(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [toJsonSafe(v, _depth + 1) for v in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (UUID, Decimal)):
        return str(value)
    if isinstance(value, Enum):
        return toJsonSafe(value.value, _depth + 1)
    # SQLAlchemy rows — mapped columns only. Relationships are skipped on purpose:
    # emitting one would lazy-load half the graph on a session that may be closed.
    # `__mapper__` is read off the class, so auto-attribute objects don't match.
    mapper = getattr(type(value), "__mapper__", None)
    if mapper is not None:
        return {
            attr.key: toJsonSafe(getattr(value, attr.key, None), _depth + 1)
            for attr in mapper.column_attrs
        }
    dump = getattr(value, "model_dump", None)  # pydantic models
    if callable(dump):
        return toJsonSafe(dump(), _depth + 1)
    return str(value)


# ── scheduling ────────────────────────────────────────────────────────────────

def _onDone(future) -> None:
    exc = future.exception()
    if exc:
        logger.exception("websocket emit failed", exc_info=exc)


def _schedule(coro) -> None:
    running: Optional[asyncio.AbstractEventLoop] = None
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        pass

    loop = running or _loop
    if loop is None:
        coro.close()
        logger.warning("no event loop bound — dropping websocket emit")
        return

    if running is not None:
        task = loop.create_task(coro)
        task.add_done_callback(_onDone)
    else:
        asyncio.run_coroutine_threadsafe(coro, loop).add_done_callback(_onDone)


def emit(event: str, data: Any, room: str, skipSid: Optional[str] = None) -> None:
    """Fire-and-forget emit to a room. Never raises into the caller's flow."""
    try:
        from websocket.socketManager import sio  # local: socketManager imports handlers

        payload = toJsonSafe(data)
        _schedule(sio.emit(event, payload, room=room, skip_sid=skipSid))
    except Exception:
        logger.exception("failed to schedule '%s' emit to room %s", event, room)


# ── chat fan-out ──────────────────────────────────────────────────────────────

def emitToChat(chatId: Any, event: str, payload: Any, participantIds: Iterable[Any]) -> None:
    """Publish a chat event to every participant's personal room.

    This used to emit to `chat_{chatId}` and then top up the personal room of
    any participant whose sid was not already in that room, deduplicating with
    `sio.manager.get_participants`. Room membership stays per-instance even
    behind the Redis manager, so that check only ever saw local sids: a
    participant connected to another instance looked absent, got the personal
    top-up as well as the room broadcast, and received the event twice.

    Every socket joins `user_{userId}` on connect, and `join_chat` refuses a
    chat the caller is not part of — so the participants' personal rooms are a
    superset of the chat room. Addressing them alone reaches every device of
    every participant exactly once, from any instance, with no membership
    lookup to get wrong.

    `chatId` is kept in the signature because callers identify the event by it
    and the payloads carry it.
    """
    for participantId in {str(p) for p in participantIds}:
        emit(event, payload, room=f"user_{participantId}")


def notifyNewMessage(message: Any, participantIds: Iterable[Any]) -> None:
    """Broadcast a freshly persisted message. Shared by REST and Socket.IO senders."""
    payload = {"message": toJsonSafe(message)}
    emitToChat(message.chat, "new_message", payload, participantIds)


def notifyMessagesRead(chatId: Any, participantIds: Iterable[Any]) -> None:
    """Broadcast that a chat's unread messages were marked read."""
    emitToChat(chatId, "messages_read", {"chatId": str(chatId)}, participantIds)


# ── friendship fan-out ────────────────────────────────────────────────────────

async def _friendshipEmit(event: str, actorId: str, targetId: str) -> None:
    from websocket import presence
    from websocket.socketManager import sio

    online = await presence.isOnline(actorId)
    await sio.emit(event, {"userId": actorId, "online": online}, room=f"user_{targetId}")


def notifyFriendship(event: str, actorId: Any, targetId: Any) -> None:
    """Tell `targetId` that `actorId` acted on their friendship.

    Called from FriendshipService, after the write that makes the event true.
    That placement is the point of this function. These events used to be
    emitted by Socket.IO handlers in `websocket/handlers/friendHandlers.py`,
    which took the target's id straight from the client and emitted into that
    user's personal room with no check that any friendship existed, that the
    caller was part of it, or that the caller was not blocked — and two of them
    sent a push notification as well. Any authenticated account could therefore
    drive unlimited pushes at any user id it could name, and a block did nothing
    to stop it. Emitting from the service means the notification cannot outrun
    the authorisation that the service already performs.

    Payload is unchanged from those handlers (`{userId, online}`), because the
    front-end listeners in `services/ws/friendship.js` read that shape.

    Fire-and-forget: a socket that cannot be reached must not roll back a
    friendship that is already committed.
    """
    actor, target = str(actorId), str(targetId)
    if not actor or not target or actor == target:
        return
    try:
        _schedule(_friendshipEmit(event, actor, target))
    except Exception:
        logger.exception("failed to schedule '%s' emit to user %s", event, target)
