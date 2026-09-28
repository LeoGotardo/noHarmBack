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
from datetime import datetime, timedelta, timezone
from uuid import uuid4


def _utcNow() -> datetime:
    """Now, as the naive UTC the schema stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

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

            # Choosing a name is what lifts the sanction. Nothing else does —
            # not acknowledging the notice, not waiting: the point was never
            # the telling-off, it was that the old name stopped being in use.
            # The generated handle counts as a name, so a user who keeps it has
            # to re-enter it deliberately, which is a decision rather than an
            # omission.
            userModel.must_change_username = False

        if profilePicture is not None:
            # A blocked picture stays blocked until a moderator lifts it.
            # Without this the sanction lasts exactly as long as it takes the
            # user to open the edit screen.
            if userModel.picture_blocked:
                raise NoHarmException(
                    statusCode=403,
                    errorCode="PICTURE_BLOCKED",
                    message="Moderation has blocked the picture on this account."
                )
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
        """Update a user's status. Logs audit type=5 (§8.1).

        This is the permanent form: banning through here leaves `banned_until`
        NULL, and moving off `banned` clears any date the account carried.
        `suspend` below is the timed one.
        """
        user = self.userRepository.updateStatus(id, status)
        actor = requestingUserId or id
        self._logAudit(5, actor, f"Account status changed to {status} for user {id}")
        return user

    def suspend(self, id: str, days: Optional[int], requestingUserId: str) -> User:
        """Ban an account for `days`, or for good when `days` is None.

        A suspension is the same `banned` status as a permanent ban plus an end
        date; it lifts itself at the first sign-in afterwards. Deliberately a
        separate call from resolving a report: closing a complaint and
        punishing an account are two decisions, and a queue where one implies
        the other makes moderators stop reading.

        `days` is capped at `MAX_SUSPENSION_DAYS`. Past that the honest action
        is a permanent ban, which someone has to choose on purpose rather than
        arrive at by typing a large number.
        """
        if days is not None and (days < 1 or days > config.MAX_SUSPENSION_DAYS):
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_SUSPENSION",
                message=f"A suspension lasts between 1 and {config.MAX_SUSPENSION_DAYS} days."
            )

        if str(id) == str(requestingUserId):
            raise NoHarmException(
                statusCode=400,
                errorCode="SELF_SUSPENSION",
                message="You cannot suspend your own account."
            )

        # Naive UTC, like `deleted_at` and every other instant in the schema:
        # the database is UTC and the app is not necessarily, so a bare
        # `datetime.now()` writes a timestamp hours off the column beside it.
        until = _utcNow() + timedelta(days=days) if days is not None else None
        user = self.userRepository.suspend(id, until)

        self._logAudit(
            5,
            requestingUserId,
            f"Account {id} suspended until {until.isoformat()}" if until
            else f"Account {id} banned permanently"
        )

        return user

    def forceUsernameChange(self, id: str, requestingUserId: str) -> User:
        """Take the username away and make the account choose another.

        The answer to an impersonating or abusive handle. A ban is far too much
        for a name and a warning is far too little — it leaves the name exactly
        where it is while the user decides whether to care.

        The account is renamed **now**, to a neutral generated handle, rather
        than being asked to fix it: the harm is the name being readable, and a
        flag alone would leave it on every friend list and chat header until the
        user next signed in. `must_change_username` is what then makes the app
        insist on a real one.

        Nothing else changes. The account is not banned, not limited, and keeps
        its streak, friends and history — the sanction is exactly as wide as the
        problem.
        """
        if str(id) == str(requestingUserId):
            raise NoHarmException(
                statusCode=400,
                errorCode="SELF_SANCTION",
                message="You cannot reset your own username."
            )

        user = self.userRepository.findById(id)  # 404 when absent
        if user.status == config.STATUS_CODES["deleted"]:
            raise NoHarmException(
                statusCode=404,
                errorCode="USER_NOT_FOUND",
                message="User not found."
            )

        previous = user.username
        updated = self.userRepository.forceUsernameChange(id, self._neutralUsername)

        # The old name is in the audit trail and in the report's evidence, and
        # nowhere else — which is the only place a moderator should have to
        # look for it.
        self._logAudit(
            5,
            requestingUserId,
            f"Username of {id} reset from '{previous}' to '{updated.username}'; user must choose a new one"
        )

        return updated

    def _neutralUsername(self) -> str:
        """A handle that says nothing about anyone.

        `user_` plus eight hex characters: inside the 3–50 length and the
        `[a-zA-Z0-9_-]` charset the profile update enforces, and far too large
        a space to collide in practice — the repository retries anyway, because
        "in practice" is not a uniqueness guarantee on a unique index.
        """
        return f"user_{uuid4().hex[:8]}"

    def setPictureBlocked(self, id: str, blocked: bool, requestingUserId: str) -> User:
        """Block or unblock the account's profile picture.

        Blocking nulls the picture as well as setting the flag, and the flag is
        the half that matters: `AuthService._syncProfilePicture` refreshes the
        photo from the Google claim at every login, so clearing the column on
        its own would undo itself the next time the user signed in.

        Unblocking does not restore anything. The old picture is gone; the next
        sign-in pulls whatever the Google account has now, which is the only
        copy that ever existed.
        """
        if str(id) == str(requestingUserId):
            raise NoHarmException(
                statusCode=400,
                errorCode="SELF_SANCTION",
                message="You cannot block your own picture."
            )

        user = self.userRepository.findById(id)  # 404 when absent
        if user.status == config.STATUS_CODES["deleted"]:
            raise NoHarmException(
                statusCode=404,
                errorCode="USER_NOT_FOUND",
                message="User not found."
            )

        updated = self.userRepository.setPictureBlocked(id, blocked)
        self._logAudit(
            5,
            requestingUserId,
            f"Profile picture of {id} {'blocked' if blocked else 'unblocked'}"
        )
        return updated

    def liftExpiredSuspension(self, id: str) -> Optional[User]:
        """Re-enable an account whose suspension ran out. None when nothing to do."""
        user = self.userRepository.liftExpiredSuspension(id)
        if user is not None:
            self._logAudit(5, str(id), f"Suspension expired for user {id}; account re-enabled")
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
