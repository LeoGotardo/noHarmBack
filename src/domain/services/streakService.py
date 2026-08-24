from infrastructure.database.repositories.streakRepository import StreakRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.repositories.userBadgesRepository import UserBadgesRepository
from infrastructure.database.repositories.badgeRepository import BadgeRepository
from infrastructure.database.models.streakModel import StreakModel
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from domain.entities.streak import Streak
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database
from typing import Optional, overload

from datetime import datetime, timezone


class StreakService:
    def __init__(self, db):
        self.database: Database = db
        self.streakRepository = StreakRepository(self.database)
        self.auditRepository = AuditLogsRepository(self.database)
        self.userBadgesRepository = UserBadgesRepository(self.database)
        self.badgeRepository = BadgeRepository(self.database)

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

    @staticmethod
    def _asUtc(value: Optional[datetime]) -> Optional[datetime]:
        """Coerce a datetime to timezone-aware UTC.

        Encrypted DateTime columns (StringEncryptedType) decrypt to *naive*
        datetimes, while everything written in-process is aware. Subtracting one
        from the other raises TypeError, so both ends are normalised before any
        arithmetic. Naive values are stored in UTC, so they are just tagged.
        """
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _durationDays(self, streak) -> float:
        start = self._asUtc(streak.start_at)
        if not start:
            return 0
        end = self._asUtc(streak.end_at) or datetime.now(timezone.utc)
        return max(0.0, (end - start).total_seconds() / 86400)

    def _checkAndGrantBadges(self, userId: str) -> None:
        """Grant every badge whose milestone the user's active streak has reached (§7.1).

        `milestone` is a number of clean days. Badges already held are skipped,
        and failures never break the streak operation that triggered the check.
        """
        try:
            streak = self.streakRepository.findCurrentStreak(userId)
        except NoHarmException:
            return

        cleanDays = self._durationDays(streak)

        try:
            badges = self.badgeRepository.findAll()
        except Exception:
            return

        # findAll returns a PaginatedResponse when given params; guard explicitly
        # rather than with an assert, which `python -O` strips out.
        if not isinstance(badges, list):
            return

        for badge in badges:
            if badge.status != config.STATUS_CODES["enabled"]:
                continue
            if badge.milestone is None or cleanDays < badge.milestone:
                continue
            try:
                if self.userBadgesRepository.existsByUserAndBadge(userId, str(badge.id)):
                    continue
                self.userBadgesRepository.grant(userId, str(badge.id), datetime.now(timezone.utc))
                self._logAudit(8, userId, f"Badge granted: {badge.name} ({badge.milestone} days)")
            except Exception:
                continue

    # ── reads ─────────────────────────────────────────────────────────────────

    def get(self, streakId: str) -> Streak:
        return self.streakRepository.findById(streakId)

    @overload
    def getAllByUserId(self, userId: str, params: None = None) -> list[Streak]: ...
    @overload
    def getAllByUserId(self, userId: str, params: PaginationParams) -> PaginatedResponse[Streak]: ...
    def getAllByUserId(self, userId: str, params: Optional[PaginationParams] = None) -> list[Streak] | PaginatedResponse[Streak]:
        return self.streakRepository.findAllByOwnerId(userId, params)

    def getCurrentByUserId(self, userId: str) -> Streak:
        try:
            streak = self.streakRepository.findCurrentStreak(userId)
        except NoHarmException as e:
            if e.statusCode == 404:
                raise NoHarmException(statusCode=404, errorCode="NO_ACTIVE_STREAK", message="No active streak found.")
            raise e

        # Clean days accrue with wall-clock time, not with user actions, so a
        # milestone can be crossed with no request in between. This read is the
        # one call every screen makes, so it doubles as the accrual trigger.
        self._checkAndGrantBadges(userId)

        return streak

    def getRecordByUserId(self, userId: str) -> Streak:
        return self.streakRepository.findCurrentRecord(userId)

    # ── mutations ─────────────────────────────────────────────────────────────

    def startStreak(self, userId: str, startAt: Optional[datetime] = None) -> Streak:
        """Create a new active streak. start_at defaults to now if not provided."""
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
            start_at=startAt or datetime.now(timezone.utc),
            end_at=None,
            last_checkin=None,
            status=config.STATUS_CODES["enabled"],
            is_record=False
        )
        created = self.streakRepository.create(newStreak)
        self._checkAndGrantBadges(userId)
        return created

    def endStreak(self, userId: str, endAt: Optional[datetime] = None) -> Streak:
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

        return self._closeAndReset(streak, userId, endAt)

    def checkin(self, userId: str) -> Streak:
        """Increment streak days by 1."""
        try:
            streak = self.streakRepository.findCurrentStreak(userId)
        except NoHarmException:
            raise NoHarmException(statusCode=404, errorCode="NO_ACTIVE_STREAK", message="No active streak found.")

        if str(streak.owner_id) != str(userId):
            raise NoHarmException(statusCode=403, errorCode="FORBIDDEN", message="Access denied.")

        updated = self.streakRepository.updateLastCheckin(str(streak.id), datetime.now(timezone.utc))
        self._checkAndGrantBadges(userId)
        return updated

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

    def _closeAndReset(self, streak, userId: str, endAt: Optional[datetime] = None) -> Streak:
        """End a streak, check record, create new streak, audit. Returns new streak."""
        now = self._asUtc(endAt) or datetime.now(timezone.utc)

        # Measure against the requested end, not "now" — the streak's own end_at
        # is still unset at this point.
        start = self._asUtc(streak.start_at)
        endedDuration = max(0.0, (now - start).total_seconds() / 86400) if start else 0.0

        # Close the streak
        self.streakRepository.updateEnd(str(streak.id), now)
        self.streakRepository.updateStatus(str(streak.id), config.STATUS_CODES["disabled"])

        # §6.2 / §6.4 — record check
        try:
            currentRecord = self.streakRepository.findCurrentRecord(userId)
            recordDuration = self._durationDays(currentRecord)
            if endedDuration > recordDuration and str(currentRecord.id) != str(streak.id):
                # findCurrentRecord returns a detached entity — mutating it and
                # committing changed nothing, so the unset goes through the repo.
                self.streakRepository.unmarkRecord(str(currentRecord.id))
                self.streakRepository.markAsRecord(str(streak.id))
        except NoHarmException:
            # No previous record → mark this one if it lasted more than 0 days
            if endedDuration > 0:
                self.streakRepository.markAsRecord(str(streak.id))

        # Audit log (§8.1 type=7)
        self._logAudit(7, userId, f"Streak reset after {endedDuration} days")

        # Create replacement streak
        newStreak = StreakModel(
            owner_id=userId,
            start_at=now,
            end_at=None,
            last_checkin=None,
            status=config.STATUS_CODES["enabled"],
            is_record=False
        )
        created = self.streakRepository.create(newStreak)  
        self._checkAndGrantBadges(userId)
        return created

