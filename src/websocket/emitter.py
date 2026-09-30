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


def _hasLoop() -> bool:
    """Whether this process has an event loop an emit could be scheduled on."""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return _loop is not None


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


# A publish-only handle on the same Redis channel the socket server consumes,
# built on first use and only when there is no event loop to schedule on.
#
# This is what lets a **separate process** reach connected clients: the cron
# jobs run as `docker compose exec app …`, with no ASGI server and no sockets of
# their own, so `_schedule` has nothing to schedule and drops the emit. Their
# alerts used to vanish exactly that quietly.
_writeOnly = None
_writeOnlyTried = False


def _publishOutOfProcess(event: str, data: Any, room: str) -> bool:
    """Emit from a process that has no socket server. True when it went out."""
    global _writeOnly, _writeOnlyTried

    if not _writeOnlyTried:
        _writeOnlyTried = True
        try:
            import socketio

            from core.config import config

            _writeOnly = socketio.RedisManager(config.REDIS_URL, write_only=True)
        except Exception:
            logger.exception("could not open a write-only socket manager")
            _writeOnly = None

    if _writeOnly is None:
        return False

    try:
        _writeOnly.emit(event, data, room=room)
        return True
    except Exception:
        logger.exception("write-only emit of '%s' failed", event)
        return False


def emit(event: str, data: Any, room: str, skipSid: Optional[str] = None) -> None:
    """Fire-and-forget emit to a room. Never raises into the caller's flow."""
    try:
        from websocket.socketManager import sio  # local: socketManager imports handlers

        payload = toJsonSafe(data)

        # No loop means no socket server in this process — a job, not the API.
        # Publishing straight onto the channel is how its alerts reach the
        # clients attached to the running instance.
        if not _hasLoop():
            if _publishOutOfProcess(event, payload, room):
                return

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


def notifyMessagesRead(chatId: Any, participantIds: Iterable[Any], readerId: Any = None) -> None:
    """Broadcast that a chat's unread messages were marked read.

    `readerId` says *who* read them: both participants get the event, and
    without it the reader's own client flipped its outgoing messages to `read`
    as well — a receipt for messages nobody had opened.
    """
    payload: dict = {"chatId": str(chatId)}
    if readerId is not None:
        payload["readerId"] = str(readerId)
    emitToChat(chatId, "messages_read", payload, participantIds)


# ── admin alerts ──────────────────────────────────────────────────────────────

def notifyAdmins(kind: str, title: str, body: str, **extra: Any) -> None:
    """Tell every administrator something happened on the machine.

    Sent to each allowlisted uid's personal room, which every one of their
    devices joins on connect. The client turns it into a browser notification —
    and only when the tab is open but not focused, which is what the existing
    notification path already does for messages.

    **This reaches an administrator who has the app open.** A closed browser
    receives nothing: there is no Web Push subscription here, and the native
    FCM path needs the installed app. For the two things this currently sends —
    a login to the host and a fault nobody has seen before — that is a real
    limitation and not a subtle one; the board is still where they are
    guaranteed to be found.

    Fire-and-forget, like every other emit: an alert that fails must never take
    down the thing it was reporting on.
    """
    try:
        from core.config import config

        for adminId in config.ADMIN_USER_IDS:
            emit(
                "admin_alert",
                {"kind": kind, "title": title, "body": body, **extra},
                room=f"user_{adminId}",
            )
    except Exception:
        logger.exception("failed to notify admins of '%s'", kind)


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


# ── community ─────────────────────────────────────────────────────────────────

def notifyPostComment(postAuthorId: Any, postId: Any, commentId: Any, commenterId: Any, commenterUsername: str) -> None:
    """Tell a post's author that someone commented on it.

    Called from PostService after the comment is written and after the
    visibility check that allowed it — the same placement rule as
    `notifyFriendship`, for the same reason. Never for the author's own
    comments, and never for likes (D6): a counter that pings is a counter
    people start watching.

    The payload names the commenter but carries no text. The client fetches
    the thread if it wants it, through the route that re-checks visibility.
    """
    author = str(postAuthorId)
    if not author or author == str(commenterId):
        return

    emit(
        "post_comment",
        {
            "post_id": str(postId),
            "comment_id": str(commentId),
            "author": {"id": str(commenterId), "username": commenterUsername},
        },
        room=f"user_{author}",
    )
