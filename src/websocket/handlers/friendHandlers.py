"""Friendship event handlers.

Server → Client:
    friend_request    {userId, online: bool}  — response per queried user
    friend_accept     {userId, online: bool}  — response per queried user
    friend_remove     {userId, online: bool}  — response per queried user
    friend_block      {userId, online: bool}  — response per queried user
    friend_unblock    {userId, online: bool}  — response per queried user
    friend_error      {code, message}         — error message
    
    
Client → Server:
    friend_request    {userId}                — send friend request
    friend_accept     {userId}                — accept friend request
    friend_reject     {userId}                — reject friend request
    friend_remove     {userId}                — remove friend
    friend_block      {userId}                — block friend
    friend_unblock    {userId}                — unblock friend

"""

import socketio

from websocket import presence

from infrastructure.external import fcmService

# python-socketio's `on()` returns the handler-setter only when called without
# a handler, so its inferred type is `((handler) -> handler) | None` and every
# `@sio.on(...)` decorator reads as "Object of type None cannot be called".
# The library ships no annotations to narrow it, hence the per-line ignores.
def register(sio: socketio.AsyncServer) -> None:
    async def _err(sid: str, code: str, msg: str) -> None:
        await sio.emit("friend_error", {"code": code, "message": msg}, to=sid)

    async def _notify(event: str, sid: str, targetUserId: str) -> None:
        session = await sio.get_session(sid)
        senderUserId: str = session.get("userId")
        await sio.emit(
            event,
            {"userId": senderUserId, "online": await presence.isOnline(senderUserId)},
            room=f"user_{targetUserId}",
        )

    @sio.on("friend_request")  # type: ignore[misc]
    async def friendRequest(sid: str, data: dict):
        userId: str | None = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_request", sid, userId)
        fcmService.sendPushToUser(userId, "New friend request", "Someone wants to connect with you")

    @sio.on("friend_accept")  # type: ignore[misc]
    async def friendAccept(sid: str, data: dict):
        userId: str | None = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_accept", sid, userId)
        fcmService.sendPushToUser(userId, "Friend request accepted", "Your friend request was accepted")

    @sio.on("friend_reject")  # type: ignore[misc]
    async def friendReject(sid: str, data: dict):
        userId: str | None = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_reject", sid, userId)

    @sio.on("friend_remove")  # type: ignore[misc]
    async def friendRemove(sid: str, data: dict):
        userId: str | None = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_remove", sid, userId)

    @sio.on("friend_block")  # type: ignore[misc]
    async def friendBlock(sid: str, data: dict):
        userId: str | None = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_block", sid, userId)

    @sio.on("friend_unblock")  # type: ignore[misc]
    async def friendUnblock(sid: str, data: dict):
        userId: str | None = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_unblock", sid, userId)