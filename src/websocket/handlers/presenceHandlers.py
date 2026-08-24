"""Presence event handlers.

Client → Server:
    get_online_status   {userIds: [...]}   — query which users are currently connected

Server → Client:
    online_status   {userId, online: bool}  — response per queried user
"""

import socketio

from websocket import presence


# python-socketio's `on()` returns the handler-setter only when called without
# a handler, so its inferred type is `((handler) -> handler) | None` and every
# `@sio.on(...)` decorator reads as "Object of type None cannot be called".
# The library ships no annotations to narrow it, hence the per-line ignores.
def register(sio: socketio.AsyncServer) -> None:

    @sio.on("get_online_status")  # type: ignore[misc]
    async def getOnlineStatus(sid: str, data: dict):
        userIds: list[str] = (data or {}).get("userIds", [])
        if not isinstance(userIds, list):
            await sio.emit("error", {"code": "INVALID_DATA", "message": "userIds must be a list"}, to=sid)
            return

        # One Redis round trip for the whole list — the old `in connectedUsers`
        # was a local dict probe and only saw sockets on this instance.
        online = await presence.onlineAmong([str(u) for u in userIds])

        for userId in userIds:
            await sio.emit(
                "online_status",
                {"userId": userId, "online": str(userId) in online},
                to=sid,
            )
            
