from infrastructure.database.repositories.friendshipRepository import FriendshipRepository
from infrastructure.database.models.friendshipModel import FriendshipModel
from domain.entities.friendship import Friendship
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database

from typing import Optional
from datetime import datetime


class FriendshipService:
    def __init__(self, db):
        self.database: Database = db
        self.friendshipRepository = FriendshipRepository(self.database)

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, friendshipId: str) -> Friendship:
        return self.friendshipRepository.findById(friendshipId)

    def getByUsers(self, userA: str, userB: str) -> Friendship:
        return self.friendshipRepository.findByUsers(userA, userB)

    def getAll(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        return self.friendshipRepository.findAllByUserId(userId, params)

    def getPendingReceived(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        return self.friendshipRepository.findPendingReceived(userId, params)

    def getPendingSent(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        return self.friendshipRepository.findPendingSent(userId, params)

    def existsByUsers(self, userA: str, userB: str) -> bool:
        return self.friendshipRepository.existsByUsers(userA, userB)

    # ── business actions ──────────────────────────────────────────────────────

    def sendRequest(self, senderId: str, receiverId: str) -> Friendship:
        """Send a friend request (§3.1).

        Rules:
        - Cannot send to self
        - Cannot send if any non-deleted friendship already exists between the two users
        - Blocked relationship → 403
        - On creation: status = pending, sendAt = now
        """
        if senderId == receiverId:
            raise NoHarmException(
                statusCode=400,
                errorCode="SELF_REQUEST",
                message="You cannot send a friend request to yourself."
            )

        try:
            existing = self.friendshipRepository.findByUsers(senderId, receiverId)
            if existing.status == config.STATUS_CODES.get("deleted"):
                # Deleted friendship can be re-initiated; fall through to create
                pass
            elif existing.status == config.STATUS_CODES.get("blocked"):
                raise NoHarmException(
                    statusCode=403,
                    errorCode="BLOCKED",
                    message="Friend request not allowed."
                )
            else:
                raise NoHarmException(
                    statusCode=409,
                    errorCode="FRIENDSHIP_EXISTS",
                    message="A friendship or pending request already exists between these users."
                )
        except NoHarmException as e:
            if e.statusCode in (403, 409):
                raise e
            # 404 → no existing friendship → safe to create

        newFriendship = FriendshipModel(
            sender=senderId,
            reciver=receiverId,
            send_at=datetime.utcnow(),
            recived_at=None,
            status=config.STATUS_CODES["pending"]
        )
        return self.friendshipRepository.create(newFriendship)

    def accept(self, friendshipId: str, receiverId: str) -> Friendship:
        """Accept a pending friend request (§3.2).

        Rules:
        - Only the receiver may accept
        - Sets status = accepted, recivedAt = now
        """
        friendship = self.friendshipRepository.findById(friendshipId)

        if str(friendship.reciver) != str(receiverId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="Only the recipient of the request can accept it."
            )

        if friendship.status != config.STATUS_CODES.get("pending"):
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_STATE",
                message="Only pending requests can be accepted."
            )

        friendship.status = config.STATUS_CODES["accepted"]
        friendship.recived_at = datetime.utcnow()
        self.friendshipRepository.session.commit()
        return friendship

    def reject(self, friendshipId: str, receiverId: str) -> Friendship:
        """Reject (ignore) a pending friend request (§3.2).

        Rules:
        - Only the receiver may reject
        - Sets status = ignored
        """
        friendship = self.friendshipRepository.findById(friendshipId)

        if str(friendship.reciver) != str(receiverId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="Only the recipient of the request can reject it."
            )

        if friendship.status != config.STATUS_CODES.get("pending"):
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_STATE",
                message="Only pending requests can be rejected."
            )

        return self.friendshipRepository.updateStatus(friendshipId, "ignored")

    def block(self, friendshipId: str, requestingUserId: str) -> Friendship:
        """Block from an existing friendship — either participant may block (§3.3).

        Rule: sets status = blocked.
        """
        friendship = self.friendshipRepository.findById(friendshipId)

        if str(friendship.sender) != str(requestingUserId) and str(friendship.reciver) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this friendship."
            )

        return self.friendshipRepository.updateStatus(friendshipId, "blocked")

    def unblock(self, friendshipId: str, requestingUserId: str) -> Friendship:
        """Unblock a previously blocked friendship (§3.3)."""
        friendship = self.friendshipRepository.findById(friendshipId)

        if str(friendship.sender) != str(requestingUserId) and str(friendship.reciver) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this friendship."
            )

        return self.friendshipRepository.updateStatus(friendshipId, "disabled")

    def delete(self, id: str, requestingUserId: str) -> bool:
        """Soft-delete a friendship — only participants may remove it (§9.1, §9.2)."""
        friendship = self.friendshipRepository.findById(id)

        if str(friendship.sender) != str(requestingUserId) and str(friendship.reciver) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this friendship."
            )

        return self.friendshipRepository.softDelete(id)

    # ── low-level passthrough (kept for admin/internal use) ───────────────────

    def updateStatus(self, id: str, status: str) -> Friendship:
        return self.friendshipRepository.updateStatus(id, status)

    def update(self, friendshipId: str, updatedFriendship: Friendship) -> Friendship:
        return self.friendshipRepository.update(friendshipId, updatedFriendship)

    def create(self, newFriendship: Friendship) -> Friendship:
        return self.friendshipRepository.create(newFriendship)
