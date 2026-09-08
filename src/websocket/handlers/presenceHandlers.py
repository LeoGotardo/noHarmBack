"""Presence event handlers.

Client → Server:
    get_online_status   {userIds: [...]}   — query which users are currently connected

Server → Client:
    online_status   {userId, online: bool}  — response per queried user
"""

import socketio

from core.database import database
from api.dependencies.database import _DbProxy
from core.config import config
from domain.services.friendshipService import FriendshipService
from infrastructure.database.rlsContext import RLSContext
from websocket import presence


# A client asks about the people on its friends list. The ceiling is well above
# any plausible list and exists to bound the work one event can buy: the reply
# is one emit per id, so an unbounded list was an amplification lever — one
# frame in, as many frames out as the sender cared to name.
_MAX_QUERY_IDS = 200


def _visibleTo(userId: str, requested: list[str]) -> set[str]:
    """Narrow `requested` to the users whose presence `userId` may see.

    Presence used to answer for any id at all, so an account could watch anyone
    it could name — including someone who had blocked it — and could sweep ids
    to learn which were real. An accepted friendship is the same bar the rest of
    the app applies to seeing another person at all.
    """
    if not requested:
        return set()

    db = _DbProxy(database.session)
    try:
        RLSContext.setUserId(db.session, userId)
        friendships = FriendshipService(db).getAll(userId)
    finally:
        db.session.close()

    acceptedStatus = config.STATUS_CODES["accepted"]
    friendIds = {
        str(f.sender) if str(f.reciver) == userId else str(f.reciver)
        for f in friendships
        if f.status == acceptedStatus
    }

    return {uid for uid in requested if uid in friendIds}


# python-socketio's `on()` returns the handler-setter only when called without
# a handler, so its inferred type is `((handler) -> handler) | None` and every
# `@sio.on(...)` decorator reads as "Object of type None cannot be called".
# The library ships no annotations to narrow it, hence the per-line ignores.
def register(sio: socketio.AsyncServer) -> None:

    @sio.on("get_online_status")  # type: ignore[misc]
    async def getOnlineStatus(sid: str, data: dict):
        session = await sio.get_session(sid)
        userId: str = session.get("userId")

        userIds: list[str] = (data or {}).get("userIds", [])
        if not isinstance(userIds, list):
            await sio.emit("error", {"code": "INVALID_DATA", "message": "userIds must be a list"}, to=sid)
            return

        if len(userIds) > _MAX_QUERY_IDS:
            await sio.emit(
                "error",
                {"code": "TOO_MANY_IDS", "message": f"At most {_MAX_QUERY_IDS} userIds per query."},
                to=sid,
            )
            return

        # Deduplicated before the friendship read: the same id repeated 200
        # times is one lookup and one answer, not 200 of each.
        requested = list({str(u) for u in userIds if u})
        visible = _visibleTo(userId, requested)

        # One Redis round trip for the whole list — the old `in connectedUsers`
        # was a local dict probe and only saw sockets on this instance.
        online = await presence.onlineAmong(sorted(visible))

        # Answered for every id the caller may see. Ids it may not see are left
        # out of the reply entirely rather than answered `false`, which would
        # still confirm the account exists.
        for userId_ in sorted(visible):
            await sio.emit(
                "online_status",
                {"userId": userId_, "online": userId_ in online},
                to=sid,
            )
