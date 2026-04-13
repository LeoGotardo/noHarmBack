from infrastructure.database.repositories.messageRepository import MessageRepository
from infrastructure.database.repositories.chatRepository import ChatRepository
from infrastructure.database.models.messageModel import MessageModel
from domain.entities.message import Message
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from security.sanitizer import Sanitizer
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database
from typing import Optional

from datetime import datetime


class MessageService:
    def __init__(self, db):
        self.database: Database = db
        self.messageRepository = MessageRepository(self.database)
        self.chatRepository = ChatRepository(self.database)

    # ── reads ─────────────────────────────────────────────────────────────────

    def getByChatId(self, chatId: str, params: Optional[PaginationParams] = None) -> list[Message] | PaginatedResponse[Message]:
        return self.messageRepository.findByChatId(chatId, params)

    def get(self, messageId: str) -> Message:
        return self.messageRepository.findById(messageId)

    def getUnreadByChatId(self, chatId: str, params: Optional[PaginationParams] = None) -> list[Message] | PaginatedResponse[Message]:
        return self.messageRepository.findUnreadByChatId(chatId, params)

    # ── send (§5.1) ───────────────────────────────────────────────────────────

    def sendMessage(self, chatId: str, senderId: str, content: str) -> Message:
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
            send_at=datetime.utcnow(),
            recived_at=None
        )
        return self.messageRepository.create(newMessage)

    # ── read receipts (§5.3) ──────────────────────────────────────────────────

    def markAsRead(self, messageId: str, requestingUserId: str) -> Message:
        """Mark a single message as read. Idempotent — already-read messages are skipped.

        Only chat participants may mark messages as read (§5.3, §9.2).
        """
        msg = self.messageRepository.findById(messageId)
        if msg.status == config.STATUS_CODES.get("read"):
            return msg
        chat = self.chatRepository.findById(str(msg.chat))
        if str(chat.sender) != str(requestingUserId) and str(chat.reciver) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this chat."
            )
        return self.messageRepository.markAsRead(messageId)

    def markAllAsRead(self, chatId: str, requestingUserId: str) -> bool:
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
        return self.messageRepository.markAllAsRead(chatId)

    # ── passthrough ───────────────────────────────────────────────────────────

    def create(self, newMessage: Message) -> Message:
        return self.messageRepository.create(newMessage)

    def updateStatus(self, messageId: str, status: int) -> Message:
        return self.messageRepository.updateStatus(messageId, status)
