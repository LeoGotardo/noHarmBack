from infrastructure.database.repositories.messageRepository import MessageRepository
from infrastructure.database.repositories.chatRepository import ChatRepository
from infrastructure.database.models.messageModel import MessageModel
from domain.services.chatService import ChatService
from domain.entities.message import Message
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from security.sanitizer import Sanitizer
from exceptions.baseExceptions import NoHarmException
from infrastructure.external import fcmService
from websocket import emitter
from core.config import config
from core.database import Database
from typing import Optional, overload

from datetime import datetime, timezone
from uuid import UUID


class MessageService:
    def __init__(self, db):
        self.database: Database = db
        self.messageRepository = MessageRepository(self.database)
        self.chatRepository = ChatRepository(self.database)

    # ── reads ─────────────────────────────────────────────────────────────────

    def _assertParticipant(self, chatId: UUID, requestingUserId: str) -> None:
        """Refuse anyone who is not one of the chat's two participants (§5.3, §9.2).

        The read endpoints used to take `currentUserId` and ignore it, leaving
        the `tb_4` RLS policy as the *only* thing standing between a chat id and
        someone else's conversation. That is the wrong shape for this codebase:
        RLS is documented as defence in depth, not the access-control layer, and
        here it was the entire layer. A role that bypasses RLS — a superuser, a
        future migration that drops the policy, a query run outside a request —
        turned `GET /messages/chat/{id}` into a way to read any conversation
        from a public id. `markAsRead` and `markAllAsRead` already checked this;
        the reads simply never did.
        """
        chat = self.chatRepository.findById(chatId)
        if str(chat.sender) != str(requestingUserId) and str(chat.reciver) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this chat."
            )

    @overload
    def getByChatId(self, chatId: UUID, requestingUserId: str, params: None = None) -> list[Message]: ...
    @overload
    def getByChatId(self, chatId: UUID, requestingUserId: str, params: PaginationParams) -> PaginatedResponse[Message]: ...
    def getByChatId(self, chatId: UUID, requestingUserId: str, params: Optional[PaginationParams] = None) -> list[Message] | PaginatedResponse[Message]:
        self._assertParticipant(chatId, requestingUserId)
        return self.messageRepository.findByChatId(chatId, params)

    def get(self, messageId: UUID) -> Message:
        return self.messageRepository.findById(messageId)

    @overload
    def getUnreadByChatId(self, chatId: UUID, requestingUserId: str, params: None = None) -> list[Message]: ...
    @overload
    def getUnreadByChatId(self, chatId: UUID, requestingUserId: str, params: PaginationParams) -> PaginatedResponse[Message]: ...
    def getUnreadByChatId(self, chatId: UUID, requestingUserId: str, params: Optional[PaginationParams] = None) -> list[Message] | PaginatedResponse[Message]:
        self._assertParticipant(chatId, requestingUserId)
        return self.messageRepository.findUnreadByChatId(chatId, params)

    # ── send (§5.1) ───────────────────────────────────────────────────────────

    def sendMessage(self, chatId: UUID, senderId: str, content: str) -> Message:
        """Send a message to a chat.

        Rules (§5.1):
        - Chat must be enabled (or pending, which auto-activates on first message)
        - Sender must be the authenticated user (ownership)
        - Content is sanitised; empty after sanitisation → 400
        - status = unread, sendAt = now
        """
        chat = self.chatRepository.findById(chatId)

        # Ownership check — sender must be a participant (§9.2)
        if str(chat.sender) != str(senderId) and str(chat.reciver) != str(senderId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this chat."
            )

        # §4.1 / §5.1 — auto-activate pending chat on first message
        if chat.status == config.STATUS_CODES.get("pending"):
            self.chatRepository.updateStatus(chatId, config.STATUS_CODES["enabled"])
        elif chat.status != config.STATUS_CODES.get("enabled"):
            raise NoHarmException(
                statusCode=400,
                errorCode="CHAT_CLOSED",
                message="Messages can only be sent to an active chat."
            )

        # §9.3 — sanitise content
        sanitised = Sanitizer.cleanHtml(content)
        if not sanitised or not sanitised.strip():
            raise NoHarmException(
                statusCode=400,
                errorCode="EMPTY_MESSAGE",
                message="Message content cannot be empty."
            )

        newMessage = MessageModel(
            chat=chatId,
            sender=senderId,
            message=sanitised.strip(),
            status=config.STATUS_CODES["unread"],
            send_at=datetime.now(timezone.utc),
            recived_at=None
        )
        created = self.messageRepository.create(newMessage)

        # §5.1 — realtime fan-out + push. Done here (not in the route or the
        # socket handler) so both send paths behave identically.
        peerId = str(chat.reciver) if str(chat.sender) == str(senderId) else str(chat.sender)
        emitter.notifyNewMessage(created, [str(chat.sender), str(chat.reciver)])
        fcmService.sendPushToUser(peerId, "New message", sanitised.strip()[:200])

        return created

    def sendMessageToUser(self, senderId: str, recipientId: str, content: str) -> Message:
        """Send a message to another user, creating the chat if none exists yet (§4.1 / §5.1).

        Resolves (or creates) the chat between the two users via ChatService.getOrCreate
        — which enforces that they are accepted friends — then delegates to sendMessage,
        which auto-activates the freshly created pending chat and persists the message.
        """
        chat = ChatService(self.database).getOrCreate(senderId, recipientId)
        return self.sendMessage(chat.id, senderId, content)

    # ── read receipts (§5.3) ──────────────────────────────────────────────────

    def markAsRead(self, messageId: UUID, requestingUserId: str) -> Message:
        """Mark a single message as read. Idempotent — already-read messages are skipped.

        Only chat participants may mark messages as read (§5.3, §9.2).
        """
        msg = self.messageRepository.findById(messageId)
        if msg.status == config.STATUS_CODES.get("read"):
            return msg
        chat = self.chatRepository.findById(msg.chat)
        if str(chat.sender) != str(requestingUserId) and str(chat.reciver) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this chat."
            )
        updated = self.messageRepository.markAsRead(messageId)
        emitter.emitToChat(
            chat.id,
            "message_read",
            {"chatId": str(chat.id), "messageId": str(messageId)},
            [str(chat.sender), str(chat.reciver)],
        )
        return updated

    def markAllAsRead(self, chatId: UUID, requestingUserId: str) -> bool:
        """Mark all unread messages in a chat as read.

        Only chat participants may perform this action (§5.3, §9.2).
        """
        chat = self.chatRepository.findById(chatId)
        if str(chat.sender) != str(requestingUserId) and str(chat.reciver) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this chat."
            )
        result = self.messageRepository.markAllAsRead(chatId)
        emitter.notifyMessagesRead(chatId, [str(chat.sender), str(chat.reciver)])
        return result

    # ── passthrough ───────────────────────────────────────────────────────────

    def create(self, newMessage: Message) -> Message:
        return self.messageRepository.create(newMessage)

    def updateStatus(self, messageId: UUID, status: int) -> Message:
        return self.messageRepository.updateStatus(messageId, status)
