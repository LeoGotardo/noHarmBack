from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.repositories.friendshipRepository import FriendshipRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from domain.entities.user import User
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from security.sanitizer import Sanitizer
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database
from typing import Optional

import re

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,50}$')


class UserService:
    def __init__(self, db):
        self.database: Database = db
        self.userRepository = UserRepository(self.database)
        self.friendshipRepository = FriendshipRepository(self.database)
        self.auditRepository = AuditLogsRepository(self.database)

    def _logAudit(self, actionType: int, catalystId: str, description: str) -> None:
        try:
            entry = AuditLogsModel(
                type=actionType,
                catalyst_id=catalystId,
                catalyst=None,
                description=description
            )
            self.auditRepository.create(entry)
        except Exception:
            pass

    # ── reads ─────────────────────────────────────────────────────────────────

    def findById(self, id: str) -> User:
        return self.userRepository.findById(id)

    def findByEmail(self, email: str) -> User:
        return self.userRepository.findByEmail(email)

    def findByUsername(self, username: str) -> User:
        return self.userRepository.findByUsername(username)

    def findAll(self, params: Optional[PaginationParams] = None) -> list[User] | PaginatedResponse[User]:
        return self.userRepository.findAll(params)

    # ── profile (§1.3) ────────────────────────────────────────────────────────

    def getProfile(self, userId: str) -> User:
        """Return the private profile of the authenticated user."""
        return self.userRepository.findById(userId)

    def getPublicProfile(self, requestingUserId: str, targetUserId: str) -> User:
        """Return a user's public profile.

        Rule §3.3: a blocked user may not load the blocker's profile.
        Both directions are checked (either user blocked the other).
        """
        # Ownership check — users always see their own profile
        if requestingUserId == targetUserId:
            return self.userRepository.findById(targetUserId)

        # Check if a blocking relationship exists between the two users
        try:
            friendship = self.friendshipRepository.findByUsers(requestingUserId, targetUserId)
            if friendship.status == config.STATUS_CODES.get("blocked"):
                raise NoHarmException(
                    statusCode=403,
                    errorCode="ACCESS_DENIED",
                    message="Profile not accessible."
                )
        except NoHarmException as e:
            if e.statusCode == 403:
                raise e
            # 404 → no friendship → access is allowed, continue

        return self.userRepository.findById(targetUserId)

    def updateProfile(self, userId: str, username: Optional[str], profilePicture: Optional[bytes]) -> User:
        """Update only the fields that users are allowed to change (§1.3).

        Only `username` and `profilePicture` may be modified.
        `email` changes require a separate verification flow (not implemented here).
        `status` changes are blocked at this endpoint — use admin endpoints.
        """
        user = self.userRepository.findById(userId)

        if username is not None:
            # §9.3 — sanitise; §1.1 — validate format
            username = Sanitizer.cleanHtml(username)
            if not _USERNAME_RE.match(username):
                raise NoHarmException(
                    statusCode=400,
                    errorCode="INVALID_USERNAME",
                    message="Username must be 3–50 characters and contain only letters, numbers, _ or -."
                )
            user.username = username
        if profilePicture is not None:
            user.profile_picture = profilePicture

        self.userRepository.session.commit()
        return user

    # ── status / delete ───────────────────────────────────────────────────────

    def create(self, User: User) -> User:
        return self.userRepository.create(User)

    def update(self, user_id: str, updatedUser: User) -> User:
        return self.userRepository.update(user_id, updatedUser)

    def updateStatus(self, id: str, status: int, requestingUserId: Optional[str] = None) -> User:
        """Update a user's status. Logs audit type=5 (§8.1)."""
        user = self.userRepository.updateStatus(id, status)
        actor = requestingUserId or id
        self._logAudit(5, actor, f"Account status changed to {status} for user {id}")
        return user

    def delete(self, userId: str, requestingUserId: str) -> bool:
        """Soft-delete a user account. Only the account owner may delete it (§1.4, §9.2)."""
        if str(userId) != str(requestingUserId):
            raise NoHarmException(
                statusCode=403,
                errorCode="FORBIDDEN",
                message="You can only delete your own account."
            )
        return self.userRepository.softDelete(userId)
