from infrastructure.database.repositories.moderationNoticeRepository import ModerationNoticeRepository
from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from domain.entities.moderationNotice import ModerationNotice
from security.sanitizer import Sanitizer
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database

from typing import Optional


# The conduct a notice can name. Same codes as a report's reason, so a warning
# can be traced back to the complaint that produced it.
NOTICE_REASONS = frozenset({
    "harassment",
    "spam",
    "inappropriate",
    "impersonation",
    "other",
})

WARNING = "warning"
SUSPENSION = "suspension"
# Two sanctions that change the account without limiting it. They get their own
# kinds rather than being warnings, because the app has to say something
# different: one of them is an instruction the user must act on before they can
# carry on, and the other is a thing that has already happened to their profile.
RENAME = "rename"
PICTURE_BLOCK = "picture"

# Audit type 5 is "account status changed"; a warning changes no status, so it
# is logged as a moderation action on the account with type 12.
_AUDIT_NOTICE = 12


class NoticeService:
    """What moderation says to the user about their own account.

    A warning is the second rung of the ladder and the one that was missing:
    before this, a moderator could ban an account or leave it alone, and
    "this is not okay, do not do it again" was a sentence with nowhere to go.

    Two rules the copy here exists to keep:

    - **It never names the reporter.** A notice says what the conduct was, not
      who complained. The promise that the reported user is never told is the
      whole reason people file reports at all, and a warning that leaks the
      complainant turns every report into a confrontation.
    - **`self_harm` is never a warning.** In a recovery app that report is
      usually a friend who is frightened for someone. Answering it with a
      telling-off is the worst available action, so it is refused here and
      routed to crisis resources instead.
    """

    def __init__(self, db):
        self.database: Database = db
        self.noticeRepository = ModerationNoticeRepository(self.database)
        self.userRepository = UserRepository(self.database)
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

    def getMine(self, userId: str, unacknowledgedOnly: bool = False) -> list[ModerationNotice]:
        return self.noticeRepository.findByUser(userId, unacknowledgedOnly)

    def countWarnings(self, userId: str) -> int:
        """How many warnings an account has had — what decides the next rung."""
        return self.noticeRepository.countWarnings(userId)

    # ── business actions ──────────────────────────────────────────────────────

    def warn(self, userId: str, reason: str, adminUserId: str, message: Optional[str] = None) -> ModerationNotice:
        """Send a warning. Nothing about the account changes.

        That is the point of the rung: the first time something happens, the
        proportionate answer is usually to say so. An app that can only ban has
        to either overreact or do nothing, and does nothing far more often.
        """
        if reason == "self_harm":
            raise NoHarmException(
                statusCode=400,
                errorCode="NOT_A_WARNING",
                message=(
                    "A report about someone's safety is not answered with a "
                    "warning. Reach out with crisis resources instead."
                )
            )

        if reason not in NOTICE_REASONS:
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_REASON",
                message="Unknown notice reason."
            )

        if str(userId) == str(adminUserId):
            raise NoHarmException(
                statusCode=400,
                errorCode="SELF_NOTICE",
                message="You cannot warn your own account."
            )

        user = self.userRepository.findById(userId)  # 404 when absent

        if user.status == config.STATUS_CODES["deleted"]:
            raise NoHarmException(
                statusCode=404,
                errorCode="USER_NOT_FOUND",
                message="User not found."
            )

        return self._issue(userId, WARNING, reason, adminUserId, message)

    def noticeOfSuspension(self, userId: str, reason: str, adminUserId: str, message: Optional[str] = None) -> Optional[ModerationNotice]:
        """Write the suspension down for the person serving it.

        Best effort: a suspension that took effect but whose notice failed to
        save is still a suspension, and failing the whole call would leave the
        moderator unsure which half happened.
        """
        try:
            return self._issue(userId, SUSPENSION, reason, adminUserId, message)
        except Exception:
            return None

    def noticeOfForcedRename(self, userId: str, reason: str, adminUserId: str, message: Optional[str] = None) -> Optional[ModerationNotice]:
        """Tell the user their username was reset and that they must pick one.

        Best effort, like a suspension's notice: the sanction is already
        self-explaining — the app will not go past the rename screen — and
        failing the call here would leave the moderator unsure whether the
        rename landed.
        """
        try:
            return self._issue(userId, RENAME, reason, adminUserId, message)
        except Exception:
            return None

    def noticeOfPictureBlock(self, userId: str, reason: str, adminUserId: str, message: Optional[str] = None) -> Optional[ModerationNotice]:
        """Tell the user their picture was removed.

        Unlike the rename, nothing in the app would otherwise say so: the photo
        is simply gone and the edit screen refuses a new one. Without this the
        user reads a moderation decision as a bug.
        """
        try:
            return self._issue(userId, PICTURE_BLOCK, reason, adminUserId, message)
        except Exception:
            return None

    def acknowledge(self, noticeId: str, userId: str) -> ModerationNotice:
        """Mark a notice read. Only its own recipient may."""
        notice = self.noticeRepository.findById(noticeId)

        if str(notice.user_id) != str(userId):
            # 404, not 403: a notice belonging to someone else is not a thing
            # this caller gets told exists.
            raise NoHarmException(
                statusCode=404,
                errorCode="NOT_FOUND",
                message="Notice not found."
            )

        return self.noticeRepository.acknowledge(noticeId)

    # ── internals ─────────────────────────────────────────────────────────────

    def _issue(self, userId: str, kind: str, reason: str, adminUserId: str, message: Optional[str]) -> ModerationNotice:
        cleaned = Sanitizer.cleanHtml(message).strip() if message else None

        notice = self.noticeRepository.create(ModerationNotice(
            user_id=userId,
            kind=kind,
            reason=(reason if reason in NOTICE_REASONS else "other"),
            message=cleaned or None,
            issued_by=adminUserId
        ))

        # Catalyst is the moderator, so the entry reads as their action. The
        # description names the conduct, never the moderator's free text and
        # never the reporter.
        self._logAudit(_AUDIT_NOTICE, adminUserId, f"{kind} sent to {userId} for {reason}")

        return notice
