from infrastructure.database.repositories.streakRepository import StreakRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.repositories.userBadgesRepository import UserBadgesRepository
from infrastructure.database.models.streakModel import StreakModel
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from domain.entities.streak import Streak
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database
from typing import Optional

from datetime import datetime, timedelta


class StreakService:
    def __init__(self, db):
        self.database: Database = db
        self.streakRepository = StreakRepository(self.database)
        self.auditRepository = AuditLogsRepository(self.database)
        self.userBadgesRepository = UserBadgesRepository(self.database)

    # ── helpers ───────────────────────────────────────────────────────────────

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

    def _durationDays(self, streak) -> float:
        """Return the length of a streak in days."""
        end = streak.end if streak.end else datetime.utcnow()
        start = streak.start
        if not start:
            return 0
        return (end - start).total_seconds() / 86400

    def _checkAndGrantBadges(self, userId: str) -> None:
        """Placeholder for badge milestone checks (§7.2 — future release).

        Called after every streak update per §7.1. Badge milestone rules
        are deferred to a future release per rules.md §7.2.
        """
        pass

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, streakId: str) -> Streak:
        return self.streakRepository.findById(streakId)

    def getAllByUserId(self, userId: str, params: Optional[PaginationParams] = None) -> list[Streak] | PaginatedResponse[Streak]:
        return self.streakRepository.findAllByOwnerId(userId, params)

    def getCurrentByUserId(self, userId: str) -> Streak:
        """Return the active streak, auto-expiring it if >24 h have passed (§6.3).

        If expired, the same end-streak flow runs: the streak is closed,
        a new one is created, badges are checked, and the new streak is returned.
        """
        try:
            streak = self.streakRepository.findCurrentStreak(userId)
        except NoHarmException as e:
            if e.statusCode == 404:
                raise NoHarmException(statusCode=404, errorCode="NO_ACTIVE_STREAK", message="No active streak found.")
            raise e

        # §6.3 — auto-expiry: check updated_at (TimestampMixin)
        lastActivity = streak.updated_at
        if lastActivity and (datetime.utcnow() - lastActivity) > timedelta(hours=24):
            # Expire and start fresh
            return self._expireAndReset(streak, userId)

        return streak

    def getRecordByUserId(self, userId: str) -> Streak:
        return self.streakRepository.findCurrentRecord(userId)

    # ── mutations ─────────────────────────────────────────────────────────────

    def startStreak(self, userId: str) -> Streak:
        """Create a new active streak for a user.

        Rules (§6.1):
        - Only one active streak allowed at a time → 409 if one exists
        - start = now, isRecord = False
        """
        try:
            existing = self.streakRepository.findCurrentStreak(userId)
            if existing:
                raise NoHarmException(
                    statusCode=409,
                    errorCode="STREAK_ALREADY_ACTIVE",
                    message="An active streak already exists. End it before starting a new one."
                )
        except NoHarmException as e:
            if e.statusCode == 409:
                raise e
            # 404 → no active streak → safe to create

        newStreak = StreakModel(
            owner_id=userId,
            start=datetime.utcnow(),
            end=None,
            status=config.STATUS_CODES["enabled"],
            is_record=False
        )
        created = self.streakRepository.create(newStreak)
        self._checkAndGrantBadges(userId)
        return created

    def endStreak(self, userId: str) -> Streak:
        """Manually end the active streak and start a fresh one (§6.2).

        Flow:
        1. Find active streak → 404 if none
        2. Set end = now, status = disabled
        3. Compare with current record; update record if longer
        4. Create new active streak
        5. Check badges
        6. Audit log type = 7
        """
        try:
            streak = self.streakRepository.findCurrentStreak(userId)
        except NoHarmException:
            raise NoHarmException(statusCode=404, errorCode="NO_ACTIVE_STREAK", message="No active streak to end.")

        return self._closeAndReset(streak, userId)

    def checkin(self, userId: str) -> Streak:
        """Refresh the streak's updated_at to prevent auto-expiry (§6.3).

        The frontend calls this once per day to confirm the user's sobriety.
        Without a daily check-in, the streak expires after 24 h of inactivity.
        """
        try:
            streak = self.streakRepository.findCurrentStreak(userId)
        except NoHarmException:
            raise NoHarmException(statusCode=404, errorCode="NO_ACTIVE_STREAK", message="No active streak found.")

        # Ownership check (§9.2)
        if str(streak.owner_id) != str(userId):
            raise NoHarmException(statusCode=403, errorCode="FORBIDDEN", message="Access denied.")

        streak.updated_at = datetime.utcnow()
        self.streakRepository.session.commit()
        return streak

    def markAsRecord(self, streakId: str) -> Streak:
        return self.streakRepository.markAsRecord(streakId)

    def create(self, newStreak: Streak) -> Streak:
        return self.streakRepository.create(newStreak)

    def updateStatus(self, streakId: str, status: int) -> None:
        self.streakRepository.updateStatus(streakId, status)

    def updateEndedAt(self, streakId: str, endedAt: datetime) -> None:
        self.streakRepository.updateEnd(streakId, endedAt)

    def delete(self, streakId: str) -> bool:
        return self.streakRepository.softDelete(streakId)

    # ── internal ──────────────────────────────────────────────────────────────

    def _closeAndReset(self, streak, userId: str) -> Streak:
        """End a streak, check record, create new streak, audit. Returns new streak."""
        now = datetime.utcnow()
        endedDuration = self._durationDays(streak)

        # Close the streak
        self.streakRepository.updateEnd(str(streak.id), now)
        self.streakRepository.updateStatus(str(streak.id), config.STATUS_CODES["disabled"])

        # §6.2 / §6.4 — record check
        try:
            currentRecord = self.streakRepository.findCurrentRecord(userId)
            recordDuration = self._durationDays(currentRecord)
            if endedDuration > recordDuration and str(currentRecord.id) != str(streak.id):
                # Unset old record
                currentRecord.is_record = False
                self.streakRepository.session.commit()
                # Mark ended streak as new record
                self.streakRepository.markAsRecord(str(streak.id))
        except NoHarmException:
            # No previous record → mark this one if it lasted more than 0 days
            if endedDuration > 0:
                self.streakRepository.markAsRecord(str(streak.id))

        # Audit log (§8.1 type=7)
        self._logAudit(7, userId, f"Streak reset after {endedDuration:.1f} days")

        # Create replacement streak
        newStreak = StreakModel(
            owner_id=userId,
            start=now,
            end=None,
            status=config.STATUS_CODES["enabled"],
            is_record=False
        )
        created = self.streakRepository.create(newStreak)
        self._checkAndGrantBadges(userId)
        return created

    def _expireAndReset(self, streak, userId: str) -> Streak:
        """Auto-expire a stale streak and start a new one (§6.3)."""
        return self._closeAndReset(streak, userId)
