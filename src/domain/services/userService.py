from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.repositories.friendshipRepository import FriendshipRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.repositories.streakRepository import StreakRepository
from infrastructure.database.repositories.userBadgesRepository import UserBadgesRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from domain.entities.user import User
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from security.sanitizer import Sanitizer
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database
from typing import Optional, overload
from datetime import datetime, timezone

import re

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,50}$')


class UserService:
    def __init__(self, db):
        self.database: Database = db
        self.userRepository = UserRepository(self.database)
        self.friendshipRepository = FriendshipRepository(self.database)
        self.auditRepository = AuditLogsRepository(self.database)
        self.streakRepository = StreakRepository(self.database)
        self.userBadgesRepository = UserBadgesRepository(self.database)

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

    @overload
    def findAll(self, params: None = None) -> list[User]: ...
    @overload
    def findAll(self, params: PaginationParams) -> PaginatedResponse[User]: ...
    def findAll(self, params: Optional[PaginationParams] = None) -> list[User] | PaginatedResponse[User]:
        return self.userRepository.findAll(params)

    @overload
    def search(self, term: str, params: None = None) -> list[User]: ...
    @overload
    def search(self, term: str, params: PaginationParams) -> PaginatedResponse[User]: ...
    def search(self, term: str, params: Optional[PaginationParams] = None) -> list[User] | PaginatedResponse[User]:
        """Find users by exact username or email (§5 — exact matches only)."""
        return self.userRepository.search(term, params)

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
            if e.statusCode != 404:
                raise

        user = self.userRepository.findById(targetUserId)

        # Deleted / banned accounts are invisible to everyone but themselves.
        if user.status in (
            config.STATUS_CODES["deleted"],
            config.STATUS_CODES["banned"],
        ):
            raise NoHarmException(statusCode=404, errorCode="NOT_FOUND", message="User not found.")

        return user

    def getPublicStats(self, requestingUserId: str, targetUserId: str) -> dict:
        """Activity numbers for a profile: active-streak days and badges held.

        Friends only. A streak is recovery data, not a public counter, and the
        screen already says "Add to see activity" — so a non-friend gets
        `visible=False` and no numbers rather than a 403, which the UI would
        have to special-case.

        `getPublicProfile` runs first so the blocked/deleted/banned rules stay in
        one place: this endpoint must not become a side channel that answers for
        a profile the caller cannot even open.

        NOTE: reads another user's rows, so the route hands it a session with no
        RLS context (`getDb`). The policies on the streak and user-badge tables
        are owner-only; the friendship check below is what authorises this, and
        it must stay in front of every read.
        """
        self.getPublicProfile(requestingUserId, targetUserId)

        if requestingUserId != targetUserId:
            try:
                friendship = self.friendshipRepository.findByUsers(requestingUserId, targetUserId)
            except NoHarmException as e:
                if e.statusCode != 404:
                    raise
                return {"visible": False, "day_streak": None, "badges_earned": None}

            if friendship.status != config.STATUS_CODES.get("accepted"):
                return {"visible": False, "day_streak": None, "badges_earned": None}

        return {
            "visible": True,
            "day_streak": self._activeStreakDays(targetUserId),
            "badges_earned": self._badgeCount(targetUserId),
        }

    def _activeStreakDays(self, userId: str) -> int:
        """Whole days of the user's active streak, or 0 when there is none.

        Floor of the elapsed time, matching what the dashboard shows its owner:
        streakService measures a streak as `end_at - start_at`, never as a count
        of check-ins.
        """
        try:
            streak = self.streakRepository.findCurrentStreak(userId)
        except NoHarmException:
            return 0
        if not streak or not streak.start_at:
            return 0

        start = streak.start_at
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - start).total_seconds() / 86400
        return max(0, int(elapsed))

    def _badgeCount(self, userId: str) -> int:
        try:
            badges = self.userBadgesRepository.findByUserId(userId)
        except NoHarmException:
            return 0
        return len(badges) if isinstance(badges, list) else 0

    def updateProfile(self, userId: str, username: Optional[str], profilePicture: Optional[str]) -> User:
        """Update only the fields that users are allowed to change (§1.3).

        Only `username` and `profilePicture` may be modified.
        `email` changes require a separate verification flow (not implemented here).
        `status` changes are blocked at this endpoint — use admin endpoints.
        """
        # returnModel=True is required: findById otherwise returns a detached
        # domain entity, so the mutations below would never reach the database
        # while the response still showed the new values.
        userModel = self.userRepository.findById(userId, returnModel=True)

        if username is not None:
            # §9.3 — sanitise; §1.1 — validate format
            username = Sanitizer.cleanHtml(username)
            if not _USERNAME_RE.match(username):
                raise NoHarmException(
                    statusCode=400,
                    errorCode="INVALID_USERNAME",
                    message="Username must be 3–50 characters and contain only letters, numbers, _ or -."
                )

            # §1.1 — usernames are globally unique; only registration checked it
            if username != userModel.username:
                try:
                    existing = self.userRepository.findByUsername(username)
                    if str(existing.id) != str(userId):
                        raise NoHarmException(
                            statusCode=409,
                            errorCode="USERNAME_TAKEN",
                            message="That username is already taken."
                        )
                except NoHarmException as e:
                    if e.statusCode != 404:
                        raise
                    # 404 → username is available

            # UserModel's @validates('username') recomputes username_hash, which
            # is what findByUsername looks up.
            userModel.username = username

        if profilePicture is not None:
            userModel.profile_picture = profilePicture

        try:
            self.userRepository.session.commit()
        except Exception:
            self.userRepository.session.rollback()
            raise

        return self.userRepository._toEntity(userModel)

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
