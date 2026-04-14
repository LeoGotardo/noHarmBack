"""Presence event handlers.

Client → Server:
    get_online_status   {userIds: [...]}   — query which users are currently connected

Server → Client:
    online_status   {userId, online: bool}  — response per queried user
"""

import socketio


def register(sio: socketio.AsyncServer, connectedUsers: dict[str, str]) -> None:

    @sio.on("get_online_status")
    async def getOnlineStatus(sid: str, data: dict):
        userIds: list[str] = (data or {}).get("userIds", [])
        if not isinstance(userIds, list):
            await sio.emit("error", {"code": "INVALID_DATA", "message": "userIds must be a list"}, to=sid)
            return

        for userId in userIds:
            await sio.emit(
                "online_status",
                {"userId": userId, "online": userId in connectedUsers},
                to=sid,
            )
