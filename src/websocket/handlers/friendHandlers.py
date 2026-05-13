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

def register(sio: socketio.AsyncServer, connectedUsers: dict[str, str]) -> None:
    async def _err(sid: str, code: str, msg: str) -> None:
        await sio.emit("friend_error", {"code": code, "message": msg}, to=sid)

    async def _notify(event: str, sid: str, targetUserId: str) -> None:
        session = await sio.get_session(sid)
        senderUserId: str = session.get("userId")
        await sio.emit(
            event,
            {"userId": senderUserId, "online": senderUserId in connectedUsers},
            room=f"user_{targetUserId}",
        )

    @sio.on("friend_request")
    async def friendRequest(sid: str, data: dict):
        userId: str = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_request", sid, userId)

    @sio.on("friend_accept")
    async def friendAccept(sid: str, data: dict):
        userId: str = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_accept", sid, userId)

    @sio.on("friend_reject")
    async def friendReject(sid: str, data: dict):
        userId: str = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_reject", sid, userId)

    @sio.on("friend_remove")
    async def friendRemove(sid: str, data: dict):
        userId: str = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_remove", sid, userId)

    @sio.on("friend_block")
    async def friendBlock(sid: str, data: dict):
        userId: str = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_block", sid, userId)

    @sio.on("friend_unblock")
    async def friendUnblock(sid: str, data: dict):
        userId: str = (data or {}).get("userId")
        if not userId:
            await _err(sid, "INVALID_DATA", "userId required")
            return
        await _notify("friend_unblock", sid, userId)