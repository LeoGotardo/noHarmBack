from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.repositories.reportRepository import ReportRepository
from infrastructure.database.repositories.reportEvidenceRepository import ReportEvidenceRepository
from infrastructure.database.repositories.moderationNoticeRepository import ModerationNoticeRepository
from infrastructure.database.repositories.consentRepository import ConsentRepository
from infrastructure.database.repositories.errorLogRepository import ErrorLogRepository
from infrastructure.database.repositories.hostAccessRepository import HostAccessRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.repositories.postRepository import PostRepository
from infrastructure.database.repositories.postCommentRepository import PostCommentRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from domain.services.consentService import ConsentService, REQUIRED_DOCUMENTS
from security.suspiciousTraffic import SuspiciousTraffic
from core.config import config
from core.database import Database

from datetime import datetime, timedelta, timezone
from typing import Optional
import json
import logging
from core.auditTypes import AuditType


logger = logging.getLogger("noharm")

# 16 is "an administrator looked at the board". Its own type rather than folding
# into 11 (evidence read): the two answer different questions — 11 is "who read
# whose messages", and mixing them would make the first hard to search for.
_AUDIT_BOARD_READ = AuditType.BOARD_READ

# How long the overview is reused. The panel is seven grouped queries, and a
# refresh is a thing people do while thinking. Long enough that hammering it
# costs one round trip a minute; short enough that a moderator acting on it is
# not reading yesterday.
_CACHE_SECONDS = 60
_CACHE_KEY = "admin:overview:v1"

# The windows the board reports sign-ups over. Cumulative on purpose: 30 days
# includes the last 7, because both are read as totals.
_SIGNUP_WINDOWS = (1, 7, 30)

# The periods the board offers, as presets rather than a free number: a reader
# reaches for "last 30 days", not for 37, and an open integer is a parameter
# that has to be range-checked on every call to stop someone asking for ten
# years of daily rows.
SERIES_PERIODS = (7, 30, 90)
DEFAULT_SERIES_DAYS = 30

# Status codes, named once here so the response speaks words rather than the
# integers `STATUS_CODES` happens to use.
_STATUS_NAMES = {
    config.STATUS_CODES["disabled"]: "disabled",
    config.STATUS_CODES["enabled"]: "enabled",
    config.STATUS_CODES["deleted"]: "deleted",
    config.STATUS_CODES["blocked"]: "blocked",
    config.STATUS_CODES["banned"]: "banned",
}
_QUEUE_NAMES = {
    config.STATUS_CODES["pending"]: "open",
    config.STATUS_CODES["accepted"]: "actioned",
    config.STATUS_CODES["ignored"]: "dismissed",
}


def _utcNow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AdminService:
    """The numbers behind the admin board.

    Two rules shape what is on it.

    **It aggregates; it does not enumerate.** There is no per-account streak
    here, no relapse, no message count. This app was built so that who is
    struggling is not something a screen can list, and an admin panel is
    exactly the screen that would undo that by accident.

    **Every field is something a person would act on.** A count that only ever
    goes up is decoration; the health panel is the opposite of that, and reads
    zero when nothing is wrong.
    """

    def __init__(self, db, redisClient=None):
        self.database: Database = db
        self.userRepository = UserRepository(self.database)
        self.reportRepository = ReportRepository(self.database)
        self.evidenceRepository = ReportEvidenceRepository(self.database)
        self.noticeRepository = ModerationNoticeRepository(self.database)
        self.consentRepository = ConsentRepository(self.database)
        self.errorRepository = ErrorLogRepository(self.database)
        self.hostAccessRepository = HostAccessRepository(self.database)
        self.auditRepository = AuditLogsRepository(self.database)
        self.postRepository = PostRepository(self.database)
        self.commentRepository = PostCommentRepository(self.database)
        self._redis = redisClient
        self._suspicious = SuspiciousTraffic(redisClient)

    # ── audit ─────────────────────────────────────────────────────────────────

    def logBoardRead(self, adminUserId: str) -> None:
        """Record that an administrator opened the board.

        Best effort, like every other audit write: a failure to log must not
        deny the read. But it is written for the same reason evidence reads are
        — a power to look that leaves no trace is indistinguishable from one
        being abused, and this board can list every account in the system.
        """
        try:
            self.auditRepository.create(
                AuditLogsModel(
                    type=_AUDIT_BOARD_READ,
                    catalyst_id=adminUserId,
                    catalyst=None,
                    description="Admin board read",
                )
            )
        except Exception:
            logger.warning("could not audit the board read", exc_info=True)

    # ── the overview ──────────────────────────────────────────────────────────

    @staticmethod
    def resolvePeriod(days: Optional[int]) -> int:
        """The requested period, or the default when it is not one we offer.

        Silently falling back rather than refusing: this scopes a dashboard, and
        a 400 for `?days=45` would break the page over a number nobody typed on
        purpose.
        """
        return days if days in SERIES_PERIODS else DEFAULT_SERIES_DAYS

    def overview(self, *, days: Optional[int] = None, useCache: bool = True) -> dict:
        """Every number on the board, from one call.

        Cached in Redis for `_CACHE_SECONDS`. The cache is best effort in both
        directions: a Redis that is down means the queries run, never that the
        board fails. It is a dashboard, and the database is the authority.
        """
        period = self.resolvePeriod(days)

        if useCache:
            cached = self._readCache(period)
            if cached is not None:
                return cached

        data = self._compute(period)

        if useCache:
            self._writeCache(period, data)

        return data

    def _compute(self, period: int) -> dict:
        now = _utcNow()

        byStatus = self.userRepository.countsByStatus()
        created = self.userRepository.countCreatedSince(*_SIGNUP_WINDOWS)
        bans = self.userRepository.countBans()
        sanctions = self.userRepository.countSanctioned()

        currentVersions = {
            document: ConsentService.currentVersion(document)
            for document in REQUIRED_DOCUMENTS
        }
        debt = self.consentRepository.countOwingReacceptance(currentVersions)

        queue = self.reportRepository.countsByStatus()
        openByReason = self.reportRepository.countOpenByReason()

        notices = self.noticeRepository.countsByKindSince(now - timedelta(days=30))

        recentAccess = self.hostAccessRepository.findRecent()

        return {
            "accounts": {
                "by_status": {
                    name: byStatus.get(code, 0) for code, name in _STATUS_NAMES.items()
                },
                # Keys as strings: this crosses JSON, where an integer key would
                # come back as a string anyway and surprise the client.
                "created": {str(days): created.get(days, 0) for days in _SIGNUP_WINDOWS},
                "bans": bans,
                "sanctions": {
                    "must_change_username": sanctions["mustChangeUsername"],
                    "picture_blocked": sanctions["pictureBlocked"],
                    "both": sanctions["both"],
                },
                "consent_debt": {
                    "documents": {
                        document: debt.get(document, 0) for document in currentVersions
                    },
                    "any": debt.get("any", 0),
                },
            },
            "moderation": {
                "queue": {
                    name: queue.get(code, 0) for code, name in _QUEUE_NAMES.items()
                },
                "open_by_reason": openByReason,
                "self_harm_open": openByReason.get("self_harm", 0),
                "stale_locks": self.reportRepository.countStaleLocks(
                    config.REPORT_LOCK_MINUTES
                ),
                "notices_30d": notices,
                "unacknowledged_notices": self.noticeRepository.countUnacknowledged(),
            },
            "health": {
                "purge_overdue": self.userRepository.countExpiredDeleted(
                    config.ACCOUNT_DELETION_GRACE_DAYS
                ),
                "evidence_overdue": self.evidenceRepository.countExpired(
                    config.REPORT_EVIDENCE_RETENTION_DAYS
                ),
                # The third retention cron. Removed posts past their window are
                # still held about their author, which the Privacy Policy says
                # they are not.
                "removed_content_overdue": self._removedContentOverdue(now),
                "error_occurrences_24h": self.errorRepository.countSince(
                    now - timedelta(hours=24)
                ),
                "distinct_faults": len(self.errorRepository.findRecent()),
                "last_host_access": (
                    recentAccess[0].occurred_at.isoformat() if recentAccess else None
                ),
            },
            "series": {
                # Daily history, every day present including the empty ones: a
                # series with the gaps removed draws a line through them and
                # turns three sign-ups in a month into a steady climb.
                "days": period,
                "periods": list(SERIES_PERIODS),
                "signups": self.userRepository.countCreatedPerDay(period),
                "reports": self.reportRepository.countCreatedPerDay(period),
                "posts": self.postRepository.countCreatedPerDay(period),
            },
            "security": {
                # A prompt to look, never an action. Blocking on these numbers
                # would let anyone deny service to a shared mobile NAT.
                "flagged_addresses": self._suspicious.flagged(),
                "window_seconds": config.SUSPICIOUS_WINDOW_SECONDS,
            },
            "generated_at": now.isoformat(),
        }

    def _removedContentOverdue(self, now: datetime) -> int:
        cutoff = now - timedelta(days=config.REMOVED_CONTENT_RETENTION_DAYS)
        return self.postRepository.countRemovedBefore(cutoff) + self.commentRepository.countRemovedBefore(cutoff)

    # ── the cache ─────────────────────────────────────────────────────────────

    def _readCache(self, period: int) -> Optional[dict]:
        if self._redis is None:
            return None
        try:
            # Keyed by period: one cache entry for every window, or switching
            # the range would hand back the previous one's numbers under the
            # new label.
            raw = self._redis.get(f"{_CACHE_KEY}:{period}")
            return json.loads(raw) if raw else None
        except Exception:
            # A cache that cannot be read is a cache miss, never an error. The
            # board's numbers live in Postgres; Redis only saves a round trip.
            logger.warning("admin overview cache unreadable", exc_info=True)
            return None

    def _writeCache(self, period: int, data: dict) -> None:
        if self._redis is None:
            return
        try:
            self._redis.setex(f"{_CACHE_KEY}:{period}", _CACHE_SECONDS, json.dumps(data))
        except Exception:
            logger.warning("admin overview cache unwritable", exc_info=True)
