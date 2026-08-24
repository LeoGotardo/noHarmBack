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
    chat_error             {code, message}
"""

import socketio

from core.database import database
from api.dependencies.database import _DbProxy
from infrastructure.database.rlsContext import RLSContext
from domain.services.messageService import MessageService
from domain.services.chatService import ChatService
from exceptions.baseExceptions import NoHarmException
from websocket.rateLimiter import wsLimit


# python-socketio's `on()` returns the handler-setter only when called without
# a handler, so its inferred type is `((handler) -> handler) | None` and every
# `@sio.on(...)` decorator reads as "Object of type None cannot be called".
# The library ships no annotations to narrow it, hence the per-line ignores.
def register(sio: socketio.AsyncServer) -> None:

    async def _err(sid: str, code: str, msg: str) -> None:
        await sio.emit("chat_error", {"code": code, "message": msg}, to=sid)

    # ── join_chat ─────────────────────────────────────────────────────────────

    @sio.on("join_chat")  # type: ignore[misc]
    async def joinChat(sid: str, data: dict):
        session = await sio.get_session(sid)
        userId: str = session.get("userId")
        chatId: str | None = (data or {}).get("chatId")

        if not chatId:
            await _err(sid, "INVALID_DATA", "chatId required")
            return

        db = _DbProxy(database.session)
        try:
            RLSContext.setUserId(db.session, userId)
            ChatService(db).get(chatId, userId)          # asserts participant
            await sio.enter_room(sid, f"chat_{chatId}")
        except NoHarmException as e:
            await _err(sid, e.errorCode, e.message)
        finally:
            db.session.close()

    # ── leave_chat ────────────────────────────────────────────────────────────

    @sio.on("leave_chat")  # type: ignore[misc]
    async def leaveChat(sid: str, data: dict):
        chatId: str | None = (data or {}).get("chatId")
        if chatId:
            await sio.leave_room(sid, f"chat_{chatId}")

    # ── send_message ──────────────────────────────────────────────────────────

    @sio.on("send_message")  # type: ignore[misc]
    @wsLimit(maxCalls=30, windowSeconds=60)
    async def sendMessage(sid: str, data: dict):
        session = await sio.get_session(sid)
        userId: str = session.get("userId")
        data = data or {}
        chatId: str | None = data.get("chatId")
        content: str | None = data.get("content")

        if not chatId or not content:
            await _err(sid, "INVALID_DATA", "chatId and content required")
            return

        db = _DbProxy(database.session)
        try:
            RLSContext.setUserId(db.session, userId)

            # Broadcast + push happen inside MessageService.sendMessage so the
            # REST and socket send paths stay identical.
            MessageService(db).sendMessage(chatId, userId, content)
        except NoHarmException as e:
            await _err(sid, e.errorCode, e.message)
        finally:
            db.session.close()

    # ── mark_read ─────────────────────────────────────────────────────────────

    @sio.on("mark_read")  # type: ignore[misc]
    async def markRead(sid: str, data: dict):
        session = await sio.get_session(sid)
        userId: str = session.get("userId")
        chatId: str | None = (data or {}).get("chatId")

        if not chatId:
            await _err(sid, "INVALID_DATA", "chatId required")
            return

        db = _DbProxy(database.session)
        try:
            RLSContext.setUserId(db.session, userId)
            # markAllAsRead broadcasts `messages_read` itself.
            MessageService(db).markAllAsRead(chatId, userId)
        except NoHarmException as e:
            await _err(sid, e.errorCode, e.message)
        finally:
            db.session.close()

    # ── typing ────────────────────────────────────────────────────────────────

    @sio.on("typing")  # type: ignore[misc]
    @wsLimit(maxCalls=60, windowSeconds=60)
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
