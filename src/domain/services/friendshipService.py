from infrastructure.database.repositories.friendshipRepository import FriendshipRepository
from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.models.friendshipModel import FriendshipModel
from domain.entities.friendship import Friendship
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from schemas.friendshipSchemas import FriendshipResponse, FriendUserInfo
from exceptions.baseExceptions import NoHarmException
from infrastructure.external import fcmService
from websocket import emitter
from core.config import config
from core.database import Database, database
from core.auditTypes import AuditType
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel

from typing import Optional, overload


class FriendshipService:
    def __init__(self, db):
        self.database: Database = db
        self.friendshipRepository = FriendshipRepository(self.database)
        self.auditRepository = AuditLogsRepository(self.database)

    def _logAudit(self, actionType: int, catalystId: str, description: str) -> None:
        """Best effort, like every other audit write: never fails the action.

        Only blocks and unblocks are recorded. They are the safety-relevant
        edges of the graph — what a moderator reviewing harassment needs to see
        in order — while requests, accepts and removals are ordinary social
        activity that an audit trail of a recovery app has no business keeping.
        """
        try:
            self.auditRepository.create(AuditLogsModel(
                type=actionType, catalyst_id=catalystId, catalyst=None, description=description
            ))
        except Exception:
            pass

    # ── notification ──────────────────────────────────────────────────────────

    @staticmethod
    def _otherParticipant(friendship: Friendship, userId: str) -> str:
        """The participant of `friendship` who is not `userId`."""
        return str(friendship.sender) if str(friendship.reciver) == str(userId) else str(friendship.reciver)

    # ── enrichment (attach each participant's name + profile picture) ──────────

    def _fetchUsersInfo(self, userIds: set[str]) -> dict[str, FriendUserInfo]:
        """Read the public profile (name + picture) of the given users.

        Uses a fresh, non-RLS session: tb_0 RLS restricts a user to their own
        row, so a friend's public profile must be read outside that context.
        """
        ids = [uid for uid in userIds if uid]
        if not ids:
            return {}
        userRepo = UserRepository(database)  # no app.current_user_id → public/admin view
        try:
            users = userRepo.findManyByIds(ids)
        finally:
            userRepo.session.close()
        return {
            u.id: FriendUserInfo(id=u.id, username=u.username, profile_picture=u.profile_picture)
            for u in users
        }

    def enrich(self, friendship: Friendship) -> FriendshipResponse:
        infoMap = self._fetchUsersInfo({friendship.sender, friendship.reciver})
        return self._buildResponse(friendship, infoMap)

    def enrichMany(self, friendships: list[Friendship]) -> list[FriendshipResponse]:
        ids: set[str] = set()
        for f in friendships:
            ids.add(f.sender)
            ids.add(f.reciver)
        infoMap = self._fetchUsersInfo(ids)
        return [self._buildResponse(f, infoMap) for f in friendships]

    def enrichPaginated(self, page: PaginatedResponse[Friendship]) -> PaginatedResponse[FriendshipResponse]:
        ids: set[str] = set()
        for f in page.items:
            ids.add(f.sender)
            ids.add(f.reciver)
        infoMap = self._fetchUsersInfo(ids)
        enriched = [self._buildResponse(f, infoMap) for f in page.items]
        # model_copy would keep the receiver's PaginatedResponse[Friendship]
        # type, and the generic is invariant, so the page is rebuilt around the
        # enriched items instead.
        return PaginatedResponse[FriendshipResponse](
            items=enriched,
            total=page.total,
            page=page.page,
            pageSize=page.pageSize,
            totalPages=page.totalPages,
            hasNext=page.hasNext,
            hasPrevious=page.hasPrevious,
        )

    @staticmethod
    def _buildResponse(friendship: Friendship, infoMap: dict[str, FriendUserInfo]) -> FriendshipResponse:
        response = FriendshipResponse.model_validate(friendship)
        response.sender_user = infoMap.get(friendship.sender)
        response.reciver_user = infoMap.get(friendship.reciver)
        return response

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, friendshipId: str) -> Friendship:
        return self.friendshipRepository.findById(friendshipId)


    def getByUsers(self, userA: str, userB: str) -> Friendship:
        return self.friendshipRepository.findByUsers(userA, userB)


    @overload
    def getAll(self, userId: str, params: None = None) -> list[Friendship]: ...
    @overload
    def getAll(self, userId: str, params: PaginationParams) -> PaginatedResponse[Friendship]: ...
    def getAll(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        return self.friendshipRepository.findAllByUserId(userId, params)


    @overload
    def getPendingReceived(self, userId: str, params: None = None) -> list[Friendship]: ...
    @overload
    def getPendingReceived(self, userId: str, params: PaginationParams) -> PaginatedResponse[Friendship]: ...
    def getPendingReceived(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        return self.friendshipRepository.findPendingReceived(userId, params)


    @overload
    def getPendingSent(self, userId: str, params: None = None) -> list[Friendship]: ...
    @overload
    def getPendingSent(self, userId: str, params: PaginationParams) -> PaginatedResponse[Friendship]: ...
    def getPendingSent(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        return self.friendshipRepository.findPendingSent(userId, params)

    @overload
    def getBlockedUsers(self, userId: str, params: None = None) -> list[Friendship]: ...
    @overload
    def getBlockedUsers(self, userId: str, params: PaginationParams) -> PaginatedResponse[Friendship]: ...
    def getBlockedUsers(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        return self.friendshipRepository.findBlockedUsers(userId, params)

    def existsByUsers(self, userA: str, userB: str) -> bool:
        return self.friendshipRepository.existsByUsers(userA, userB)
    

    # ── business actions ──────────────────────────────────────────────────────

    def sendRequest(self, senderId: str, receiverId: str) -> Friendship:
        """Send a friend request (§3.1).

        Rules:
        - Cannot send to self
        - Cannot send if a live friendship (pending, accepted, ignored) already
          exists between the two users
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
            if existing.status in (
                config.STATUS_CODES.get("deleted"),
                config.STATUS_CODES.get("disabled"),
            ):
                # A deleted friendship can be re-initiated, and so can a lifted
                # block: `clearBlock` leaves the row `disabled` on purpose — an
                # unblock restores nothing — so it is history, not a live
                # request. Treating it as one answered 409 "already exists" to
                # a pair the app (rightly) showed as strangers, forever.
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
            status=config.STATUS_CODES["pending"]
        )
        created = self.friendshipRepository.create(newFriendship)

        # Only reached once the checks above have passed, which is what the
        # socket handler that used to send this never did: it pushed to whatever
        # id the client named. Everything before this line — not sending to
        # yourself, no duplicate request, not blocked — is now a precondition of
        # the notification too.
        emitter.notifyFriendship("friend_request", senderId, receiverId)
        fcmService.sendPushToUser(receiverId, "New friend request", "Someone wants to connect with you", category="friends")

        return created


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

        accepted = self.friendshipRepository.updateStatus(friendshipId, "accepted")

        emitter.notifyFriendship("friend_accept", receiverId, str(friendship.sender))
        fcmService.sendPushToUser(str(friendship.sender), "Friend request accepted", "Your friend request was accepted", category="friends")

        return accepted


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

        rejected = self.friendshipRepository.updateStatus(friendshipId, "ignored")

        # No push, matching the previous behaviour: a rejection is delivered to
        # an open app or not at all.
        emitter.notifyFriendship("friend_reject", receiverId, str(friendship.sender))

        return rejected


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

        if friendship.status == config.STATUS_CODES.get("blocked"):
            # Already blocked — by this user, or by the other one. Either way
            # both are hidden from each other, and re-stamping `blocked_by`
            # would hand the unblock to whoever asked second.
            return friendship

        blocked = self.friendshipRepository.setBlocked(friendshipId, requestingUserId)

        otherId = self._otherParticipant(friendship, requestingUserId)
        self._logAudit(AuditType.USER_BLOCKED, requestingUserId, f"Blocked {otherId}")
        emitter.notifyFriendship("friend_block", requestingUserId, otherId)

        return blocked


    def unblock(self, friendshipId: str, requestingUserId: str) -> Friendship:
        """Unblock a previously blocked friendship (§3.3).

        Only whoever blocked may unblock. Before `blocked_by` existed either
        participant could, which meant the blocked one could undo it; rows from
        that time have no record of who blocked and keep the old rule.
        """
        friendship = self.friendshipRepository.findById(friendshipId)

        if str(friendship.sender) != str(requestingUserId) and str(friendship.reciver) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this friendship."
            )
            
        if friendship.status != config.STATUS_CODES.get("blocked"):
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_STATE",
                message="Only blocked requests can be unblocked."
            )

        self._assertMayUnblock(friendship, requestingUserId)

        unblocked = self.friendshipRepository.clearBlock(friendshipId)

        otherId = self._otherParticipant(friendship, requestingUserId)
        self._logAudit(AuditType.USER_UNBLOCKED, requestingUserId, f"Unblocked {otherId}")
        emitter.notifyFriendship("friend_unblock", requestingUserId, otherId)

        return unblocked


    @staticmethod
    def _assertMayUnblock(friendship: Friendship, requestingUserId: str) -> None:
        if friendship.blocked_by is not None and str(friendship.blocked_by) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="Only the person who blocked can unblock."
            )


    # ── blocking anyone, friend or not (§1.1 of docs/POSTS_PLAN.md) ──────────

    def blockUser(self, requestingUserId: str, targetId: str) -> Friendship:
        """Block an account whether or not there is a friendship with it.

        Blocking used to exist only on top of a friendship row, which was
        enough while only friends could reach each other. In the Community tab a
        stranger can comment on you, and without this there was no way to stop
        them. An existing row between the two is moved to blocked; otherwise
        one is created for the purpose.

        No push and nothing visible to the blocked account. The `friend_block`
        socket event still goes out, and the app only refetches its list on it.
        """
        if str(requestingUserId) == str(targetId):
            raise NoHarmException(
                statusCode=400,
                errorCode="SELF_BLOCK",
                message="You cannot block yourself."
            )

        # 404 for an account that does not exist. A deleted or banned one can
        # still be blocked: that is exactly the account that may come back.
        UserRepository(self.database).findById(targetId)

        rows = self.friendshipRepository.findAllBetween(requestingUserId, targetId)

        existing = next((r for r in rows if r.status == config.STATUS_CODES["blocked"]), None)
        if existing is not None:
            return existing

        # The live row if there is one — deleted rows are history, and blocking
        # on top of one would leave an accepted friendship beside the block.
        live = next((r for r in rows if r.status != config.STATUS_CODES["deleted"]), None)
        if live is not None:
            blocked = self.friendshipRepository.setBlocked(str(live.id), requestingUserId)
        else:
            blocked = self.friendshipRepository.create(FriendshipModel(
                sender=requestingUserId,
                reciver=targetId,
                status=config.STATUS_CODES["blocked"],
                blocked_by=requestingUserId
            ))

        self._logAudit(AuditType.USER_BLOCKED, requestingUserId, f"Blocked {targetId}")
        emitter.notifyFriendship("friend_block", requestingUserId, targetId)

        return blocked


    def unblockUser(self, requestingUserId: str, targetId: str) -> Friendship:
        """Lift a block by the other account's id. Only whoever blocked may."""
        rows = self.friendshipRepository.findAllBetween(requestingUserId, targetId)

        blockedRow = next((r for r in rows if r.status == config.STATUS_CODES["blocked"]), None)
        if blockedRow is None:
            raise NoHarmException(
                statusCode=404,
                errorCode="NOT_BLOCKED",
                message="This user is not blocked."
            )

        self._assertMayUnblock(blockedRow, requestingUserId)

        unblocked = self.friendshipRepository.clearBlock(str(blockedRow.id))

        self._logAudit(AuditType.USER_UNBLOCKED, requestingUserId, f"Unblocked {targetId}")
        emitter.notifyFriendship("friend_unblock", requestingUserId, targetId)

        return unblocked


    def delete(self, id: str, requestingUserId: str) -> bool:
        """Soft-delete a friendship — only participants may remove it (§9.1, §9.2)."""
        friendship = self.friendshipRepository.findById(id)

        if str(friendship.sender) != str(requestingUserId) and str(friendship.reciver) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You are not a participant in this friendship."
            )

        # Captured before the delete: `friendship` is the only handle on who the
        # other participant was.
        peerId = self._otherParticipant(friendship, requestingUserId)

        removed = self.friendshipRepository.softDelete(id)

        emitter.notifyFriendship("friend_remove", requestingUserId, peerId)

        return removed


    # ── low-level passthrough (kept for admin/internal use) ───────────────────

    def updateStatus(self, id: str, status: str) -> Friendship:
        return self.friendshipRepository.updateStatus(id, status)

    def update(self, friendshipId: str, updatedFriendship: Friendship) -> Friendship:
        return self.friendshipRepository.update(friendshipId, updatedFriendship)

    def create(self, newFriendship: Friendship) -> Friendship:
        return self.friendshipRepository.create(newFriendship)
