from infrastructure.database.repositories.chatRepository import ChatRepository
from infrastructure.database.repositories.friendshipRepository import FriendshipRepository
from infrastructure.database.models.chatModel import ChatModel
from domain.entities.chat import Chat
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database

from datetime import datetime
from sqlalchemy import or_


class ChatService:
    def __init__(self, db):
        self.database: Database = db
        self.chatRepository = ChatRepository(self.database)
        self.friendshipRepository = FriendshipRepository(self.database)

    # ── reads ─────────────────────────────────────────────────────────────────

    def getAllByUserId(self, userId: str) -> list[Chat]:
        """Return all chats where the user is sender or receiver."""
        sent = self.chatRepository.findAllBySenderId(userId)
        received = self.chatRepository.findAllByReciverId(userId)
        return sent + received

    def get(self, chatId: str, requestingUserId: str) -> Chat:
        """Return a chat, verifying the requesting user is a participant (§9.2)."""
        chat = self.chatRepository.findById(chatId)
        self._assertParticipant(chat, requestingUserId)
        return chat

    # ── creation / activation ─────────────────────────────────────────────────

    def getOrCreate(self, senderId: str, receiverId: str) -> Chat:
        """Return existing active chat or create a new one between two users (§4.1).

        Rules:
        - Users must be accepted friends (§3.4)
        - If an active (pending or enabled) chat already exists, return it (no duplicate)
        - New chat starts with status = pending
        """
        # §3.4 — friendship must be accepted
        try:
            friendship = self.friendshipRepository.findByUsers(senderId, receiverId)
        except NoHarmException:
            raise NoHarmException(
                statusCode=403,
                errorCode="NOT_FRIENDS",
                message="A chat can only be started between accepted friends."
            )

        if friendship.status != config.STATUS_CODES.get("accepted"):
            raise NoHarmException(
                statusCode=403,
                errorCode="NOT_FRIENDS",
                message="A chat can only be started between accepted friends."
            )

        # §4.1 — check for existing active chat
        existing = self._findActiveChatBetween(senderId, receiverId)
        if existing:
            return existing

        newChat = ChatModel(
            sender=senderId,
            reciver=receiverId,
            started_at=datetime.utcnow(),
            ended_at=None,
            status=config.STATUS_CODES["pending"]
        )
        return self.chatRepository.create(newChat)

    def activate(self, chatId: str, requestingUserId: str) -> Chat:
        """Activate a pending chat (pending → enabled) (§4.1).

        Either participant may activate the chat by sending the first message
        or by explicitly accepting the chat invitation.
        """
        chat = self.chatRepository.findById(chatId)
        self._assertParticipant(chat, requestingUserId)

        if chat.status != config.STATUS_CODES.get("pending"):
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_STATE",
                message="Only pending chats can be activated."
            )

        self.chatRepository.updateStatus(chatId, config.STATUS_CODES["enabled"])
        return self.chatRepository.findById(chatId)

    # ── ending ────────────────────────────────────────────────────────────────

    def endChat(self, chatId: str, requestingUserId: str) -> Chat:
        """End a chat — either participant may close it (§4.2).

        Sets endedAt = now, status = disabled.
        """
        chat = self.chatRepository.findById(chatId)
        self._assertParticipant(chat, requestingUserId)

        self.chatRepository.updateEndedAt(chatId, datetime.utcnow())
        self.chatRepository.updateStatus(chatId, config.STATUS_CODES["disabled"])
        return self.chatRepository.findById(chatId)

    # ── passthrough (legacy / admin) ──────────────────────────────────────────

    def create(self, newChat: Chat) -> Chat:
        return self.chatRepository.create(newChat)

    def updateStatus(self, chatId: str, status: int) -> Chat:
        self.chatRepository.updateStatus(chatId, status)

    def update(self, chatId: str, updatedChat: Chat) -> Chat:
        return self.chatRepository.update(chatId, updatedChat)

    def updateEndedAt(self, chatId: str, endedAt: datetime) -> Chat:
        self.chatRepository.updateEndedAt(chatId, endedAt)

    def delete(self, chatId: str, requestingUserId: str) -> bool:
        """Soft-delete a chat — only participants may delete it (§4.3, §9.2)."""
        chat = self.chatRepository.findById(chatId)
        self._assertParticipant(chat, requestingUserId)
        return self.chatRepository.softDelete(chatId)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _assertParticipant(self, chat, userId: str) -> None:
        """Raise 403 if userId is not a participant of the chat (§9.2)."""
        if str(chat.sender) != str(userId) and str(chat.reciver) != str(userId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this chat."
            )

    def _findActiveChatBetween(self, userA: str, userB: str):
        """Find an active (pending or enabled) chat between two users."""
        active_statuses = {config.STATUS_CODES.get("pending"), config.STATUS_CODES.get("enabled")}

        sent = self.chatRepository.findAllBySenderId(userA)
        for chat in sent:
            if str(chat.reciver) == str(userB) and chat.status in active_statuses:
                return chat

        received = self.chatRepository.findAllByReciverId(userA)
        for chat in received:
            if str(chat.sender) == str(userB) and chat.status in active_statuses:
                return chat

        return None
