"""Chat event handlers.

Client → Server:
    join_chat       {chatId}                    — join chat room for real-time updates
    leave_chat      {chatId}                    — leave chat room
    send_message    {chatId, content}           — send message; broadcasts new_message
    mark_read       {chatId}                    — mark all unread messages in chat as read
    typing          {chatId, isTyping: bool}    — forward typing indicator to peer

Server → Client:
    new_message       {message}
    messages_read     {chatId}
    typing_indicator  {chatId, userId, isTyping}
    error             {code, message}
"""

import dataclasses
import socketio

from core.database import database
from infrastructure.database.rlsContext import RLSContext
from domain.services.messageService import MessageService
from domain.services.chatService import ChatService
from exceptions.baseExceptions import NoHarmException


def register(sio: socketio.AsyncServer, connectedUsers: dict[str, str]) -> None:

    async def _err(sid: str, code: str, msg: str) -> None:
        await sio.emit("error", {"code": code, "message": msg}, to=sid)

    # ── join_chat ─────────────────────────────────────────────────────────────

    @sio.on("join_chat")
    async def joinChat(sid: str, data: dict):
        session = await sio.get_session(sid)
        userId: str = session.get("userId")
        chatId: str | None = (data or {}).get("chatId")

        if not chatId:
            await _err(sid, "INVALID_DATA", "chatId required")
            return

        db = database.session
        try:
            RLSContext.setUserId(db, userId)
            ChatService(db).get(chatId, userId)          # asserts participant
            sio.enter_room(sid, f"chat_{chatId}")
        except NoHarmException as e:
            await _err(sid, e.errorCode, e.message)
        finally:
            db.close()

    # ── leave_chat ────────────────────────────────────────────────────────────

    @sio.on("leave_chat")
    async def leaveChat(sid: str, data: dict):
        chatId: str | None = (data or {}).get("chatId")
        if chatId:
            sio.leave_room(sid, f"chat_{chatId}")

    # ── send_message ──────────────────────────────────────────────────────────

    @sio.on("send_message")
    async def sendMessage(sid: str, data: dict):
        session = await sio.get_session(sid)
        userId: str = session.get("userId")
        data = data or {}
        chatId: str | None = data.get("chatId")
        content: str | None = data.get("content")

        if not chatId or not content:
            await _err(sid, "INVALID_DATA", "chatId and content required")
            return

        db = database.session
        try:
            RLSContext.setUserId(db, userId)

            message = MessageService(db).sendMessage(chatId, userId, content)
            payload = {"message": dataclasses.asdict(message)}

            # deliver to all sids in the chat room
            await sio.emit("new_message", payload, room=f"chat_{chatId}")

            # also push to the peer's personal room if not in the chat room
            chat = ChatService(db).get(chatId, userId)
            peerId = str(chat.reciver) if str(chat.sender) == userId else str(chat.sender)
            peerSid = connectedUsers.get(peerId)
            if peerSid:
                roomMembers = sio.manager.get_participants("/", f"chat_{chatId}")
                if peerSid not in roomMembers:
                    await sio.emit("new_message", payload, room=f"user_{peerId}")

        except NoHarmException as e:
            await _err(sid, e.errorCode, e.message)
        finally:
            db.close()

    # ── mark_read ─────────────────────────────────────────────────────────────

    @sio.on("mark_read")
    async def markRead(sid: str, data: dict):
        session = await sio.get_session(sid)
        userId: str = session.get("userId")
        chatId: str | None = (data or {}).get("chatId")

        if not chatId:
            await _err(sid, "INVALID_DATA", "chatId required")
            return

        db = database.session
        try:
            RLSContext.setUserId(db, userId)
            MessageService(db).markAllAsRead(chatId, userId)
            await sio.emit("messages_read", {"chatId": chatId}, room=f"chat_{chatId}")
        except NoHarmException as e:
            await _err(sid, e.errorCode, e.message)
        finally:
            db.close()

    # ── typing ────────────────────────────────────────────────────────────────

    @sio.on("typing")
    async def typing(sid: str, data: dict):
        session = await sio.get_session(sid)
        userId: str = session.get("userId")
        data = data or {}
        chatId: str | None = data.get("chatId")
        isTyping: bool = bool(data.get("isTyping", False))

        if not chatId:
            await _err(sid, "INVALID_DATA", "chatId required")
            return

        await sio.emit(
            "typing_indicator",
            {"chatId": chatId, "userId": userId, "isTyping": isTyping},
            room=f"chat_{chatId}",
            skip_sid=sid,
        )
