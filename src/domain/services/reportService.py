from infrastructure.database.repositories.reportRepository import ReportRepository
from infrastructure.database.repositories.reportEvidenceRepository import ReportEvidenceRepository
from infrastructure.database.repositories.chatRepository import ChatRepository
from infrastructure.database.repositories.messageRepository import MessageRepository
from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.repositories.postRepository import PostRepository
from infrastructure.database.repositories.postCommentRepository import PostCommentRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from domain.entities.report import Report
from domain.entities.reportEvidence import ReportEvidence
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from security.sanitizer import Sanitizer
from security.rateLimiter import ReportQuotaLimiter
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database

import json
import logging

from datetime import datetime, timedelta, timezone
from typing import Optional, overload
from uuid import UUID


# Mirrors `ReportReason` in schemas/reportSchemas.py. Pydantic rejects anything
# else at the route, and this second copy keeps the rule with the business logic
# for callers that are not a route (a future admin tool, a socket handler).
REPORT_REASONS = frozenset({
    "harassment",
    "spam",
    "inappropriate",
    "impersonation",
    "self_harm",
    "other",
})

# Statuses reused from STATUS_CODES rather than invented: a report is `pending`
# while nobody has looked at it, `accepted` once a moderator acted on it, and
# `ignored` once one dismissed it.
_OPEN = "pending"
_RESOLUTIONS = ("accepted", "ignored")

# Audit log type for "user reported another user" (§7.5). 1/2 are login, 5 is a
# status change, 6 a logout, 7 a streak reset, 8 a badge grant.
_AUDIT_REPORT = 10

# Type 11 is a moderator opening the evidence behind a report. It is logged for
# the same reason the evidence exists at all: reading it means reading private
# messages between two users, and an unlogged power to do that is indist-
# inguishable from an abused one.
_AUDIT_EVIDENCE_READ = 11

# How much of a conversation is copied when a report names a chat. Both sides,
# not only the reported user's lines: a recorte of one half is not evidence of
# anything, and the exchange is what says whether a message was provocation or
# reply.
_EVIDENCE_MESSAGE_WINDOW = 20

# Reports a moderator dismissed are the ones a cooldown applies to; an actioned
# one never blocks the next report about the same person.
_DISMISSED = "ignored"

logger = logging.getLogger("noharm.reports")

# One ceiling per account, shared across instances. Module-level like
# `authService._loginLimiter`, for the same reason: it holds no per-request
# state, and the tests patch this name.
_reportLimiter = ReportQuotaLimiter()


def _lockHeldBy(report) -> Optional[str]:
    """Who is reviewing this report right now, if anyone.

    A lock older than `REPORT_LOCK_MINUTES` is no lock at all. Without the
    expiry, a moderator who closed the tab parks a report for ever and the only
    way back is a hand-written UPDATE — so the clock is what keeps the queue
    self-healing.
    """
    if not report.locked_by or report.locked_at is None:
        return None

    age = datetime.now(timezone.utc).replace(tzinfo=None) - report.locked_at
    if age > timedelta(minutes=config.REPORT_LOCK_MINUTES):
        return None

    return report.locked_by


class ReportService:
    def __init__(self, db):
        self.database: Database = db
        self.reportRepository = ReportRepository(self.database)
        self.evidenceRepository = ReportEvidenceRepository(self.database)
        self.chatRepository = ChatRepository(self.database)
        self.messageRepository = MessageRepository(self.database)
        self.userRepository = UserRepository(self.database)
        self.postRepository = PostRepository(self.database)
        self.commentRepository = PostCommentRepository(self.database)
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

    def get(self, reportId: str) -> Report:
        return self.reportRepository.findById(reportId)

    @overload
    def getMine(self, reporterId: str, params: None = None) -> list[Report]: ...
    @overload
    def getMine(self, reporterId: str, params: PaginationParams) -> PaginatedResponse[Report]: ...
    def getMine(self, reporterId: str, params: Optional[PaginationParams] = None) -> list[Report] | PaginatedResponse[Report]:
        return self.reportRepository.findByReporter(reporterId, params)

    @overload
    def getAll(self, status: Optional[int] = None, params: None = None, sort: str = "newest") -> list[Report]: ...
    @overload
    def getAll(self, status: Optional[int], params: PaginationParams, sort: str = "newest") -> PaginatedResponse[Report]: ...
    def getAll(
        self,
        status: Optional[int] = None,
        params: Optional[PaginationParams] = None,
        sort: str = "newest"
    ) -> list[Report] | PaginatedResponse[Report]:
        """The moderation queue (admin). `sort` is `newest` or `priority`."""
        return self.reportRepository.findAll(status, params, sort)

    def countAgainst(self, reportedId: str, openOnly: bool = True) -> int:
        """How many reports name a user (admin)."""
        return self.reportRepository.countByReported(
            reportedId,
            config.STATUS_CODES[_OPEN] if openOnly else None
        )

    def signalsFor(self, reports: list[Report]) -> dict[str, dict]:
        """What the queue shows beside each report, keyed by report id.

        Two things a moderator cannot see from the row itself:

        - **who filed it** — how their previous reports were decided. A
          reporter with nine dismissals is not thereby wrong on the tenth, but
          a moderator reading it without that number is missing the question.
        - **how many others filed one** — the count of open reports naming the
          same account. Past `REPORT_BRIGADING_THRESHOLD` it is flagged.

        The flag is a prompt to look, never an action. Suspending an account
        because a number got large is precisely what a coordinated group is
        trying to buy, and it is also what an account with one genuinely bad
        week looks like. Resolving a report still changes nothing on its own.

        Two grouped queries for the whole page, not two per row.
        """
        if not reports:
            return {}

        reporterIds = list({r.reporter for r in reports if r.reporter})
        reportedIds = list({r.reported_uid for r in reports if r.reported_uid})

        standings = self.reportRepository.standingsByReporters(reporterIds)
        openAgainst = self.reportRepository.countOpenAgainstMany(reportedIds)
        # A third grouped query, for the same reason as the other two: the row
        # carries the reporter's id, and an id is not something a moderator can
        # weigh. Missing ids are purged accounts and stay missing.
        reporterNames = self.userRepository.usernamesByIds(reporterIds)
        threshold = config.REPORT_BRIGADING_THRESHOLD

        signals: dict[str, dict] = {}
        for report in reports:
            tally = standings.get(report.reporter) if report.reporter else None
            openCount = openAgainst.get(report.reported_uid, 0) if report.reported_uid else 0

            signals[str(report.id)] = {
                # None, not zeroes, once the reporter's account is purged: "no
                # history" and "we no longer know" are different answers, and
                # showing the second as the first invents a clean record.
                "reporter_standing": self._standing(tally) if tally is not None else None,
                "reporter_username": reporterNames.get(report.reporter) if report.reporter else None,
                "open_against_reported": openCount,
                "looks_coordinated": openCount >= threshold,
            }

        return signals

    @staticmethod
    def _standing(tally: dict[str, int]) -> dict:
        """Turn a reporter's decided/undecided tallies into the queue's figure.

        `weight` is smoothed — `(accepted + 1) / (accepted + ignored + 2)` — so
        a reporter with no decided history sits at 0.5. Unsmoothed, a first
        report would score zero and sort below every established reporter's,
        which is the opposite of what a new user filing a real complaint
        deserves. `pending` is deliberately not in it: a report nobody has read
        says nothing about the person who filed it.
        """
        accepted = tally.get("accepted", 0)
        ignored = tally.get("ignored", 0)
        pending = tally.get("pending", 0)

        return {
            "filed": accepted + ignored + pending,
            "accepted": accepted,
            "ignored": ignored,
            "pending": pending,
            "weight": (accepted + 1) / (accepted + ignored + 2),
        }

    # ── business actions ──────────────────────────────────────────────────────

    def report(
        self,
        reporterId: str,
        reportedId: str,
        reason: str,
        details: Optional[str] = None,
        chatId: Optional[UUID] = None,
        postId: Optional[UUID] = None,
        commentId: Optional[UUID] = None
    ) -> Report:
        """File a report about another user.

        Rules:
        - Cannot report yourself
        - The reporter's own account has to be enabled — an unverified account
          is a throwaway, and a throwaway that can file reports is a free one
        - Within the reporter's hourly and daily quota, and within the number of
          reports they may leave unreviewed at once
        - The reported account has to exist and not be deleted
        - One open report per pair, and none for a while after a moderator
          dismissed the last one about the same person
        - `details` is user prose about someone else, so it is sanitised on the
          way in and encrypted at rest

        `chatId` names the conversation the report is about. The client sends an
        **id and nothing else**: the messages are copied out of the database
        here. Accepting the text from the client would make a report a box in
        which to type quotes and attribute them to someone.

        Reporting deliberately does *not* block, unfriend or notify anyone. The
        reported user is never told, which is the point: a report that warns its
        subject is one people stop filing.

        ## Why the ceilings are here and not only on the route

        `@limiter.limit("5/minute")` on `POST /reports/{id}` keys on the client
        IP. One account reporting a different person every twelve seconds never
        trips it, and a reporter on a shared mobile carrier NAT trips it because
        of strangers. Everything below keys on the reporter instead.

        None of it refuses a *first* report about someone, and none of it is
        ever the difference between a safety report being filed and not: the
        quotas are tens per day, and the pair cooldown only follows a moderator
        deciding the last one was baseless.

        ## Posts and comments

        `postId` / `commentId` name what in the Community tab the report is
        about. The same rules as `chatId`: an id and never the text, the target
        has to be visible to the reporter (404 otherwise), and it has to have
        been written by the person being reported (400
        `REPORT_TARGET_MISMATCH`). They exclude each other and combine with
        `chatId`.

        **D8 — a second report with something new in it.** A reporter whose
        report about this person is still open gets a 409 for a second one,
        which is right for the same complaint and wrong for a new post: the
        second offensive post would never reach the moderator. So a filing that
        names a post or comment while a report is open adds that as evidence to
        the open report and answers with it, `appended=True`. It spends no
        quota — nothing new was filed — and is not held back by the backlog
        cap for the same reason.
        """
        if reporterId == reportedId:
            raise NoHarmException(
                statusCode=400,
                errorCode="SELF_REPORT",
                message="You cannot report yourself."
            )

        if reason not in REPORT_REASONS:
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_REASON",
                message="Unknown report reason."
            )

        if postId is not None and commentId is not None:
            raise NoHarmException(
                statusCode=400,
                errorCode="REPORT_TARGET_AMBIGUOUS",
                message="Report a post or a comment, not both."
            )

        if postId is not None or commentId is not None:
            appended = self._appendToOpenReport(reporterId, reportedId, postId, commentId, details)
            if appended is not None:
                return appended

        # Redis before Postgres: the cheapest refusal comes first, and an
        # account already over its quota should not cost a user lookup per
        # attempt.
        allowed, quotaMessage = _reportLimiter.check(reporterId)
        if not allowed:
            raise NoHarmException(
                statusCode=429,
                errorCode="REPORT_QUOTA_EXCEEDED",
                message=quotaMessage or "You have filed too many reports. Try again later."
            )

        self._assertReporterEligible(reporterId)
        self._assertBacklogUnderCap(reporterId)

        reported = self.userRepository.findById(reportedId)  # 404 when absent

        if reported.status == config.STATUS_CODES["deleted"]:
            raise NoHarmException(
                statusCode=404,
                errorCode="USER_NOT_FOUND",
                message="User not found."
            )

        self._assertPairAllowed(reporterId, reportedId)

        # Validated before the report exists, not during capture: a refusal
        # after the row was written would answer 403 while leaving a filed
        # report behind, and the retry would then come back 409.
        if chatId is not None:
            self._assertChatBetween(chatId, reporterId, reportedId)

        # Same placement and the same reason: resolved and checked before the
        # report exists.
        target = self._resolveTarget(reporterId, reportedId, postId, commentId)

        cleaned = Sanitizer.cleanHtml(details).strip() if details else None

        created = self.reportRepository.create(Report(
            reporter=reporterId,
            reported=reportedId,
            reported_uid=reportedId,
            reported_username=reported.username,
            reason=reason,
            details=cleaned or None,
            status=config.STATUS_CODES[_OPEN],
            target_kind=(
                "comment" if commentId is not None
                else "post" if postId is not None
                else "chat" if chatId is not None
                else None
            )
        ))

        # Charged here, not at the check: a reporter turned away by the
        # duplicate rule or by an unknown user has learned something the app
        # should have known, and spending their allowance on it punishes the
        # wrong person. Requests refused before this line are the per-IP
        # limiter's problem.
        _reportLimiter.spend(reporterId)

        self._captureEvidence(created, reported, chatId, target)

        # Catalyst is the reporter: tb_7's select policy is catalyst-only, so
        # the entry is readable by the person who filed it and by nobody else.
        # The description names the reason, never the free text.
        self._logAudit(_AUDIT_REPORT, reporterId, f"Reported user {reportedId} for {reason}")

        return created

    # ── the abuse ceilings ────────────────────────────────────────────────────

    def _assertReporterEligible(self, reporterId: str) -> None:
        """Refuse a reporter whose own account is not in good standing.

        Google sign-in always arrives verified, so a real user is `enabled` from
        the first second and never meets this. What it closes is the provider
        that does not verify an address: without it, an unverified account is a
        free one, and a free account that can file reports is a free
        harassment tool.

        A reporter whose row is gone is refused rather than treated as valid:
        `getCurrentUser` should have caught it, and disagreeing with the token
        is the safer direction.
        """
        try:
            reporter = self.userRepository.findById(reporterId)
        except NoHarmException:
            raise NoHarmException(
                statusCode=403,
                errorCode="REPORTER_NOT_ELIGIBLE",
                message="This account cannot file reports."
            )

        if reporter.status != config.STATUS_CODES["enabled"]:
            raise NoHarmException(
                statusCode=403,
                errorCode="REPORTER_NOT_ELIGIBLE",
                message="Verify your account before reporting someone."
            )

    def _assertBacklogUnderCap(self, reporterId: str) -> None:
        """Refuse a reporter who already has `REPORT_MAX_OPEN` awaiting review.

        The quota limits the rate; this limits the standing backlog. Without it
        an account inside its quota still fills the queue faster than moderators
        empty it, and the ones that get buried are everybody else's.

        It clears itself: every report a moderator closes gives the reporter a
        slot back, so someone with a genuine list of complaints files them as
        the queue moves rather than all at once.
        """
        openCount = self.reportRepository.countByReporter(
            reporterId,
            config.STATUS_CODES[_OPEN]
        )

        if openCount >= config.REPORT_MAX_OPEN:
            raise NoHarmException(
                statusCode=429,
                errorCode="TOO_MANY_OPEN_REPORTS",
                message=(
                    f"You have {openCount} reports waiting to be reviewed. "
                    "Please wait for our team to look at them before filing another."
                )
            )

    def _assertPairAllowed(self, reporterId: str, reportedId: str) -> None:
        """What the reporter's last report about this person means for the next.

        Three outcomes, three answers:

        - **still open** — a duplicate. The same 409 as before: one unreviewed
          complaint per pair, so nobody buries the queue under one grievance.
        - **dismissed recently** — refused until `REPORT_DISMISSED_COOLDOWN_DAYS`
          have passed. This is the hole the open-only check left: "ignored" was
          a round trip, and refiling the moment a moderator closed it put the
          same complaint back in front of the next one, indefinitely.
        - **actioned, or dismissed long ago** — allowed. A report that was
          actioned is *evidence the reporter was right*, and making them wait
          before reporting a repeat offender would be exactly backwards.
        """
        last = self.reportRepository.findRecentByPair(reporterId, reportedId)
        if last is None:
            return

        if last.status == config.STATUS_CODES[_OPEN]:
            raise NoHarmException(
                statusCode=409,
                errorCode="REPORT_ALREADY_OPEN",
                message="You already reported this user. Our team is looking into it."
            )

        if last.status != config.STATUS_CODES[_DISMISSED]:
            return  # actioned — nothing to cool down

        # `updated_at` is when the moderator closed it. The clock starts at the
        # decision, not at the filing: a report that sat in the queue for three
        # weeks must not arrive already cooled down.
        decidedAt = last.updated_at or last.created_at
        if decidedAt is None:
            return

        cooldownEnds = decidedAt + timedelta(days=config.REPORT_DISMISSED_COOLDOWN_DAYS)
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        if cooldownEnds <= now:
            return

        raise NoHarmException(
            statusCode=409,
            errorCode="REPORT_RECENTLY_DISMISSED",
            message=(
                "Our team reviewed your last report about this user and took no action. "
                "If something new has happened, please contact support."
            ),
            details={"canReportAgainAt": cooldownEnds.isoformat() + "Z"}
        )

    # ── evidence ──────────────────────────────────────────────────────────────

    def getEvidence(self, reportId: str, adminUserId: str) -> list[ReportEvidence]:
        """What was captured when a report was filed — admin only.

        Every call is logged (type 11). The evidence is private messages between
        two users who did not consent to a third reader; the log is what makes
        that power reviewable instead of merely available.
        """
        report = self.reportRepository.findById(reportId)  # 404 when absent

        evidence = self.evidenceRepository.findByReport(report.id)

        self._logAudit(
            _AUDIT_EVIDENCE_READ,
            adminUserId,
            f"Read {len(evidence)} evidence item(s) for report {reportId}"
        )

        return evidence

    def _captureEvidence(self, report: Report, reported, chatId: Optional[UUID], target: Optional[list] = None) -> None:
        """Copy what the report is about, at the moment it is filed.

        Two kinds of item:

        - `profile` — who the reported account was right then. Always captured:
          a username and picture are what an impersonation report *is*, and both
          can be changed in the seconds after a report is filed.
        - `message` — the tail of the named conversation, both sides.
        - `post` / `comment` — the Community item named, as it read when the
          report was filed. A comment brings its post too: a reply with no
          context is half a conversation, the same argument as copying both
          sides of a chat.

        Capture runs on the request's own session, which carries the reporter's
        RLS context: `tb_3` and `tb_4` are participant-scoped, so a reporter can
        only ever capture a conversation they are themselves in.
        `_assertChatBetween` has already said the same thing with a readable
        error, before the report existed.

        **A failure here never fails the report.** A filed report with no
        evidence is a weaker record; a report refused because the copy broke is
        no record at all, and the person filing it has already decided
        something happened.
        """
        try:
            items: list[ReportEvidence] = [
                ReportEvidence(
                    report=report.id,
                    kind="profile",
                    source_id=reported.id,
                    author_id=reported.id,
                    content=json.dumps({
                        "username": reported.username,
                        "profile_picture": reported.profile_picture,
                        "status": reported.status,
                    }, ensure_ascii=False)
                )
            ]

            if chatId is not None:
                items.extend(self._captureChat(chatId, report.id))

            items.extend(self._targetEvidence(target or [], report.id))

            self.evidenceRepository.createMany(items)
        except Exception:
            logger.exception("evidence capture failed for report %s", report.id)

    def _assertChatBetween(self, chatId: UUID, reporterId: str, reportedId: str) -> None:
        """Refuse a conversation that is not this pair's.

        `tb_3` is participant-scoped by RLS, so a chat belonging to two other
        people is already a 404 here rather than a leak. These checks exist to
        answer with the reason, and to stop a reporter attaching a conversation
        that has nothing to do with the person they are reporting.
        """
        chat = self.chatRepository.findById(chatId)  # 404 when absent
        participants = (chat.sender, chat.reciver)

        if reporterId not in participants:
            raise NoHarmException(
                statusCode=403,
                errorCode="NOT_A_PARTICIPANT",
                message="You can only report a conversation you are part of."
            )

        if reportedId not in participants:
            raise NoHarmException(
                statusCode=400,
                errorCode="UNRELATED_CHAT",
                message="That conversation does not involve the reported user."
            )

    def _captureChat(self, chatId: UUID, reportId) -> list[ReportEvidence]:
        """The tail of a chat, as evidence items. Both sides, oldest first."""
        messages = self.messageRepository.findRecentByChatId(chatId, _EVIDENCE_MESSAGE_WINDOW)

        return [
            ReportEvidence(
                report=reportId,
                kind="message",
                source_id=str(message.id),
                author_id=message.sender,
                content=message.message,
                occurred_at=message.send_at or message.created_at
            )
            for message in messages
        ]

    # ── posts and comments as evidence ────────────────────────────────────────

    def _resolveTarget(
        self,
        reporterId: str,
        reportedId: str,
        postId: Optional[UUID],
        commentId: Optional[UUID]
    ) -> list:
        """The post or comment a report names, checked, as `[(kind, row), ...]`.

        A comment comes back with its post after it, so both are captured.
        Visibility is the reporter's: something they cannot see is a 404
        exactly as it is on the post routes, so a report cannot be used to
        learn that a hidden post exists.
        """
        if commentId is not None:
            comment = self.commentRepository.findVisible(commentId, reporterId)
            if str(comment.author_id) != str(reportedId):
                raise self._targetMismatch()
            post = self.postRepository.findById(comment.post_id)
            return [("comment", comment), ("post", post)]

        if postId is not None:
            post = self.postRepository.findVisible(postId, reporterId)
            if str(post.author_id) != str(reportedId):
                raise self._targetMismatch()
            return [("post", post)]

        return []

    @staticmethod
    def _targetMismatch() -> NoHarmException:
        return NoHarmException(
            statusCode=400,
            errorCode="REPORT_TARGET_MISMATCH",
            message="That was not written by the user you are reporting."
        )

    @staticmethod
    def _targetEvidence(target: list, reportId) -> list[ReportEvidence]:
        return [
            ReportEvidence(
                report=reportId,
                kind=kind,
                source_id=str(row.id),
                author_id=row.author_id,
                content=row.content,
                occurred_at=row.created_at
            )
            for kind, row in target
        ]

    def _appendToOpenReport(
        self,
        reporterId: str,
        reportedId: str,
        postId: Optional[UUID],
        commentId: Optional[UUID],
        details: Optional[str]
    ) -> Optional[Report]:
        """D8: add a post or comment to the open report instead of a 409.

        Returns None when there is no open report to add to, and the caller
        files a new one as usual.

        Only the post or comment is captured — the conversation, if the
        original report named one, is already there. The reporter's `details`
        become a `note` item rather than being dropped: the report already has
        their first account in its own column, and this is the second.
        """
        last = self.reportRepository.findRecentByPair(reporterId, reportedId)
        if last is None or last.status != config.STATUS_CODES[_OPEN]:
            return None

        self._assertReporterEligible(reporterId)

        target = self._resolveTarget(reporterId, reportedId, postId, commentId)
        items = self._targetEvidence(target, last.id)

        note = Sanitizer.cleanHtml(details).strip() if details else None
        if note:
            items.append(ReportEvidence(
                report=last.id,
                kind="note",
                source_id=None,
                author_id=reporterId,
                content=note,
                occurred_at=datetime.now(timezone.utc).replace(tzinfo=None)
            ))

        # Unlike capture at filing, a failure here is the whole request: there
        # is no new report standing to fall back on.
        self.evidenceRepository.createMany(items)

        self._logAudit(
            _AUDIT_REPORT,
            reporterId,
            f"Added {target[0][0]} evidence to report {last.id}"
        )

        last.appended = True
        return last

    # ── the review lock ───────────────────────────────────────────────────────

    def claim(self, reportId: str, adminUserId: str) -> Report:
        """Take a report for review, so a second moderator does not duplicate it.

        Refused when someone else holds a live lock (409), and when the report
        has already been reviewed (400) — there is nothing left to decide.
        Re-claiming your own is fine and simply restarts the clock, which is
        what a moderator still working on it should do.
        """
        report = self.reportRepository.findById(reportId)  # 404 when absent

        if report.status != config.STATUS_CODES[_OPEN]:
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_STATE",
                message="This report has already been reviewed."
            )

        holder = _lockHeldBy(report)
        if holder is not None and holder != adminUserId:
            raise NoHarmException(
                statusCode=409,
                errorCode="REPORT_LOCKED",
                message="Another moderator is reviewing this report."
            )

        claimed = self.reportRepository.claim(reportId, adminUserId)
        self._logAudit(_AUDIT_REPORT, adminUserId, f"Report {reportId} claimed for review")

        return claimed

    def release(self, reportId: str, adminUserId: str) -> Report:
        """Put a report back in the queue without deciding anything.

        Only the holder releases it — or anyone, once the lock has expired,
        since by then it is not held at all.
        """
        report = self.reportRepository.findById(reportId)

        holder = _lockHeldBy(report)
        if holder is not None and holder != adminUserId:
            raise NoHarmException(
                statusCode=409,
                errorCode="REPORT_LOCKED",
                message="Another moderator is reviewing this report."
            )

        released = self.reportRepository.releaseLock(reportId)
        self._logAudit(_AUDIT_REPORT, adminUserId, f"Report {reportId} released without a decision")

        return released

    def resolve(self, reportId: str, status: str, adminUserId: str) -> Report:
        """Close a report — admin only (`accepted` = actioned, `ignored` = dismissed).

        Banning the reported account is a separate, deliberate step:
        `PUT /users/{id}/status/{status}`. Resolving a report never changes an
        account on its own.
        """
        if status not in _RESOLUTIONS:
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_STATE",
                message="A report can only be actioned or dismissed."
            )

        report = self.reportRepository.findById(reportId)

        if report.status != config.STATUS_CODES[_OPEN]:
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_STATE",
                message="This report has already been reviewed."
            )

        # Deciding on a report someone else is reading is the collision the lock
        # exists to prevent — and the one that ends with two punishments for one
        # offence. Claiming is not mandatory: an unheld report resolves as it
        # always did, so a single moderator never has to think about locks.
        holder = _lockHeldBy(report)
        if holder is not None and holder != adminUserId:
            raise NoHarmException(
                statusCode=409,
                errorCode="REPORT_LOCKED",
                message="Another moderator is reviewing this report."
            )

        resolved = self.reportRepository.updateStatus(reportId, status)

        self._logAudit(_AUDIT_REPORT, adminUserId, f"Report {reportId} resolved as {status}")

        return resolved
