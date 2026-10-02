from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.repositories.badgeRepository import BadgeRepository
from infrastructure.database.repositories.chatRepository import ChatRepository
from infrastructure.database.repositories.consentRepository import ConsentRepository
from infrastructure.database.repositories.friendshipRepository import FriendshipRepository
from infrastructure.database.repositories.messageRepository import MessageRepository
from infrastructure.database.repositories.moderationNoticeRepository import ModerationNoticeRepository
from infrastructure.database.repositories.notificationRepository import NotificationRepository
from infrastructure.database.repositories.postRepository import PostRepository
from infrastructure.database.repositories.postCommentRepository import PostCommentRepository
from infrastructure.database.repositories.reportRepository import ReportRepository
from infrastructure.database.repositories.streakRepository import StreakRepository
from infrastructure.database.repositories.userBadgesRepository import UserBadgesRepository
from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database

from datetime import date, datetime, timezone
from typing import Any, Optional
from core.auditTypes import AuditType


# What the export format itself is. Bumped when the shape changes, so a file
# someone downloaded a year ago can still be told apart from a current one.
EXPORT_VERSION = "1"

_AUDIT_DATA_EXPORT = AuditType.DATA_EXPORT


def _iso(value: Optional[datetime | date]) -> Optional[str]:
    """Timestamps as ISO 8601, nulls preserved.

    Stored instants are naive UTC (see the note in CLAUDE.md), so the `Z` is
    added rather than derived — `isoformat()` on a naive value prints no offset
    and would read as local time to whoever opens the file.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    return value.isoformat()


def _utcNow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ExportService:
    """Everything this system holds about one account, as one JSON document.

    The right of access is the only one of the data-protection rights this app
    could not answer: deleting is `DELETE /users/me`, correcting is
    `PUT /users/me`, and "show me what you have" had no implementation at all.

    ## What is in it

    The profile, the consent history, streaks, friendships, badges, device
    registrations, moderation notices addressed to this account, the reports it
    filed, its audit trail, its posts, comments and likes, and its conversations — **including messages the
    other person sent**. A thread with one side removed is not a record of a
    conversation, and the user read those messages when they arrived; the
    export is not showing them anything new.

    ## What is deliberately left out, and why

    - **Reports filed *about* this account, and the evidence behind them.** The
      promise that a reported user is never told who complained is what makes
      reporting usable at all, and an export is a particularly bad place to
      break it: it is a file, it gets forwarded, and the reporter has no say.
      Moderation notices are included, because those were already shown to the
      user and name conduct rather than a person.
    - **The identity of people this account reported.** The reporter's own words
      are their data and are included; the name of the person they accused is
      not needed for the user to understand their own record, and an export
      carrying accusations tied to names is a liability the moment the file
      leaves the device.
    - **Device push tokens.** A registration is listed — when, and whether it is
      live — without the token itself. The token is a credential: anyone
      holding it can send push notifications to that device, and writing
      credentials into a file the user is about to download and email to
      themselves makes the export the weakest link in the system.
    - **Anything belonging to another account.** Friendships and chats name the
      other participant by the uid the app already shows; nothing else about
      them is read.

    ## Why it is synchronous

    One account's data is small — thousands of rows at the very top end — and
    the alternative is a job, a queue, a storage bucket and an email service to
    deliver the link. There is no email service. A single request that reads and
    returns is the honest shape for this size, and the rate limit on the route
    is what keeps it from being a way to make the database work.
    """

    def __init__(self, db):
        self.database: Database = db
        self.userRepository = UserRepository(self.database)
        self.consentRepository = ConsentRepository(self.database)
        self.streakRepository = StreakRepository(self.database)
        self.friendshipRepository = FriendshipRepository(self.database)
        self.userBadgesRepository = UserBadgesRepository(self.database)
        self.badgeRepository = BadgeRepository(self.database)
        self.chatRepository = ChatRepository(self.database)
        self.messageRepository = MessageRepository(self.database)
        self.notificationRepository = NotificationRepository(self.database)
        self.noticeRepository = ModerationNoticeRepository(self.database)
        self.reportRepository = ReportRepository(self.database)
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

    # ── the whole thing ───────────────────────────────────────────────────────

    def exportFor(self, userId: str) -> dict:
        """Assemble the export. Raises 404 if the account is not there.

        Every section below is independent and failure in one must not lose the
        rest: an export that returns nothing because the badge catalogue had a
        bad row answers the request with less than a partial answer would. Each
        section that fails comes back as `null` with its name listed in
        `incomplete`, so the file says which part is missing rather than
        pretending it was empty.
        """
        user = self.userRepository.findById(userId)  # 404 when absent

        sections: dict[str, Any] = {}
        incomplete: list[str] = []

        for name, build in (
            ("profile", lambda: self._profile(user)),
            ("consents", lambda: self._consents(userId)),
            ("streaks", lambda: self._streaks(userId)),
            ("friendships", lambda: self._friendships(userId)),
            ("badges", lambda: self._badges(userId)),
            ("conversations", lambda: self._conversations(userId)),
            ("posts", lambda: self._posts(userId)),
            ("comments", lambda: self._comments(userId)),
            ("likes", lambda: self._likes(userId)),
            ("devices", lambda: self._devices(userId)),
            ("moderation_notices", lambda: self._notices(userId)),
            ("reports_filed", lambda: self._reportsFiled(userId)),
            ("activity_log", lambda: self._auditTrail(userId)),
        ):
            try:
                sections[name] = build()
            except Exception:
                sections[name] = None
                incomplete.append(name)

        self._logAudit(_AUDIT_DATA_EXPORT, userId, "Account data exported")

        return {
            "export_version": EXPORT_VERSION,
            "generated_at": _iso(_utcNow()),
            "account_id": str(user.id),
            # Empty for a healthy export. Present always, so a consumer never
            # has to tell "no key" from "no failures".
            "incomplete": incomplete,
            "notes": {
                "omitted": [
                    "Reports filed about this account, and the material behind them: "
                    "the people who filed them are never identified to the account "
                    "they are about.",
                    "The identity of accounts this user reported.",
                    "Push notification tokens: a token is a credential for the device "
                    "that holds it, and this file is not a place to keep credentials.",
                ],
                "included_from_others": (
                    "Conversations carry both sides. Messages the other participant "
                    "sent are part of the record of a conversation this account took "
                    "part in and had already read."
                ),
            },
            **sections,
        }

    # ── sections ──────────────────────────────────────────────────────────────

    def _profile(self, user) -> dict:
        return {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "profile_picture": user.profile_picture,
            "birth_date": _iso(user.birth_date),
            "status": user.status,
            "created_at": _iso(user.created_at),
            "updated_at": _iso(user.updated_at),
            "deleted_at": _iso(user.deleted_at),
            "banned_until": _iso(user.banned_until),
            "must_change_username": bool(user.must_change_username),
            "picture_blocked": bool(user.picture_blocked),
        }

    def _consents(self, userId: str) -> list[dict]:
        return [
            {
                "document": consent.document,
                "version": consent.version,
                "accepted_at": _iso(consent.accepted_at),
                "withdrawn_at": _iso(consent.withdrawn_at),
            }
            for consent in self.consentRepository.findByUser(userId)
        ]

    def _streaks(self, userId: str) -> list[dict]:
        streaks = self.streakRepository.findAllByOwnerId(userId)
        return [
            {
                "id": str(streak.id),
                "start_at": _iso(streak.start_at),
                "end_at": _iso(streak.end_at),
                "last_checkin": _iso(streak.last_checkin),
                "is_record": bool(streak.is_record),
                "status": streak.status,
                "created_at": _iso(streak.created_at),
            }
            for streak in streaks
        ]

    def _friendships(self, userId: str) -> list[dict]:
        friendships = self.friendshipRepository.findAllByUserId(userId)
        return [
            {
                "id": str(friendship.id),
                # Which side this account was on decides whether it sent the
                # request or received it, and that is the only thing the row
                # says that the other uid does not.
                "direction": "sent" if str(friendship.sender) == str(userId) else "received",
                "other_user_id": str(friendship.reciver if str(friendship.sender) == str(userId) else friendship.sender),
                "status": friendship.status,
                "created_at": _iso(friendship.created_at),
                "updated_at": _iso(friendship.updated_at),
            }
            for friendship in friendships
        ]

    def _badges(self, userId: str) -> list[dict]:
        held = self.userBadgesRepository.findByUserId(userId)

        entries = []
        for userBadge in held:
            # The catalogue row is what makes the grant readable — a bare badge
            # uuid tells the user nothing. A missing one is not worth failing
            # the section over.
            name = None
            milestone = None
            try:
                badge = self.badgeRepository.findById(str(userBadge.badge_id))
                name = badge.name
                milestone = badge.milestone
            except Exception:
                pass

            entries.append({
                "badge_id": str(userBadge.badge_id),
                "name": name,
                "milestone_days": milestone,
                "given_at": _iso(userBadge.given_at),
                "status": userBadge.status,
            })

        return entries

    def _conversations(self, userId: str) -> list[dict]:
        chats = self.chatRepository.findByParticipant(userId)

        conversations = []
        for chat in chats:
            otherId = chat.reciver if str(chat.sender) == str(userId) else chat.sender

            try:
                messages = self.messageRepository.findByChatId(chat.id)
            except Exception:
                messages = []

            conversations.append({
                "id": str(chat.id),
                "other_user_id": str(otherId),
                "opened_by_me": str(chat.sender) == str(userId),
                "started_at": _iso(chat.started_at),
                "ended_at": _iso(chat.ended_at),
                "status": chat.status,
                "messages": [
                    {
                        "id": str(message.id),
                        "from_me": str(message.sender) == str(userId),
                        "body": message.message,
                        "sent_at": _iso(message.send_at),
                        "created_at": _iso(message.created_at),
                        "status": message.status,
                    }
                    for message in messages
                ],
            })

        return conversations

    def _posts(self, userId: str) -> list[dict]:
        """Every post this account wrote — **including** ones a moderator removed.

        A removed post still exists for REMOVED_CONTENT_RETENTION_DAYS, and the
        right of access covers data for as long as it is held, not only while
        it is on display. `removed_at` says which is which.
        """
        return [
            {
                "id": str(post.id),
                "content": post.content,
                "visibility": post.visibility,
                "removed_by_moderation": post.status == config.STATUS_CODES["blocked"],
                "removed_at": _iso(post.removed_at),
                "created_at": _iso(post.created_at),
            }
            for post in self.postRepository.findAllByAuthor(userId)
        ]

    def _comments(self, userId: str) -> list[dict]:
        """This account's comments, removed ones included, for the same reason.

        Other people's comments on this account's posts are not here: they are
        someone else's words, and unlike a conversation the author never
        addressed them to this user alone.
        """
        return [
            {
                "id": str(comment.id),
                "post_id": str(comment.post_id),
                "content": comment.content,
                "removed_by_moderation": comment.status == config.STATUS_CODES["blocked"],
                "removed_at": _iso(comment.removed_at),
                "created_at": _iso(comment.created_at),
            }
            for comment in self.commentRepository.findAllByAuthor(userId)
        ]

    def _likes(self, userId: str) -> list[dict]:
        return [
            {"post_id": str(postId), "liked_at": _iso(likedAt)}
            for postId, likedAt in self.postRepository.likedPostIds(userId)
        ]

    def _devices(self, userId: str) -> dict:
        """Device registrations, counted — never the tokens themselves."""
        tokens = self.notificationRepository.findActiveByUserId(userId)
        return {
            "active_registrations": len(tokens),
            "note": (
                "Push tokens are omitted on purpose: a token lets its holder send "
                "notifications to that device."
            ),
        }

    def _notices(self, userId: str) -> list[dict]:
        return [
            {
                "kind": notice.kind,
                "reason": notice.reason,
                "message": notice.message,
                "acknowledged_at": _iso(notice.acknowledged_at),
                "created_at": _iso(notice.created_at),
                # `issued_by` is left out for the same reason the API leaves it
                # out: which moderator decided is not part of what the account
                # was told.
            }
            for notice in self.noticeRepository.findByUser(userId)
        ]

    def _reportsFiled(self, userId: str) -> list[dict]:
        reports = self.reportRepository.findByReporter(userId)
        return [
            {
                "id": str(report.id),
                "reason": report.reason,
                "details": report.details,
                "status": report.status,
                "target_kind": report.target_kind,
                "created_at": _iso(report.created_at),
                # No `reported`, `reported_uid` or `reported_username`: see the
                # class docstring.
            }
            for report in reports
        ]

    def _auditTrail(self, userId: str) -> list[dict]:
        entries = self.auditRepository.findByCatalystId(userId)
        return [
            {
                "type": entry.type,
                "description": entry.description,
                "created_at": _iso(entry.created_at),
            }
            for entry in entries
        ]
