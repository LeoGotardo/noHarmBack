"""Unit tests for ExportService.

Most of these assert what the export does **not** contain. That is where the
decisions are: the file is downloadable, forwardable, and leaves the system, so
every field in it is a field somebody else might end up reading.
"""

import pytest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.exportService import ExportService
    service = ExportService(mock_db)
    for name in (
        "userRepository", "consentRepository", "streakRepository",
        "friendshipRepository", "userBadgesRepository", "badgeRepository",
        "chatRepository", "messageRepository", "notificationRepository",
        "noticeRepository", "reportRepository", "auditRepository",
    ):
        setattr(service, name, MagicMock())

    service.userRepository.findById.return_value = _mock_user()
    service.consentRepository.findByUser.return_value = []
    service.streakRepository.findAllByOwnerId.return_value = []
    service.friendshipRepository.findAllByUserId.return_value = []
    service.userBadgesRepository.findByUserId.return_value = []
    service.chatRepository.findByParticipant.return_value = []
    service.messageRepository.findByChatId.return_value = []
    service.notificationRepository.findActiveByUserId.return_value = []
    service.noticeRepository.findByUser.return_value = []
    service.reportRepository.findByReporter.return_value = []
    service.auditRepository.findByCatalystId.return_value = []
    return service


def _mock_user(uid="uid-001"):
    u = MagicMock()
    u.id = uid
    u.username = "someone"
    u.email = "someone@test.com"
    u.profile_picture = None
    u.birth_date = date(1990, 6, 15)
    u.status = 1
    u.created_at = datetime(2026, 1, 1)
    u.updated_at = datetime(2026, 1, 2)
    u.deleted_at = None
    u.banned_until = None
    u.must_change_username = False
    u.picture_blocked = False
    return u


def _mock_message(sender, body="hello", msgId="msg-1"):
    m = MagicMock()
    m.id = msgId
    m.sender = sender
    m.message = body
    m.send_at = datetime(2026, 2, 1)
    m.created_at = datetime(2026, 2, 1)
    m.status = 8
    return m


# ── shape ─────────────────────────────────────────────────────────────────────

def test_export_of_an_unknown_account_is_a_404(mock_db):
    service = _make_service(mock_db)
    service.userRepository.findById.side_effect = NoHarmException(statusCode=404, message="User not found")

    with pytest.raises(NoHarmException) as exc:
        service.exportFor("uid-nobody")

    assert exc.value.statusCode == 404


def test_a_healthy_export_lists_nothing_as_incomplete(mock_db):
    service = _make_service(mock_db)

    export = service.exportFor("uid-001")

    assert export["incomplete"] == []
    assert export["account_id"] == "uid-001"


def test_one_broken_section_does_not_lose_the_rest(mock_db):
    """A partial export must say which part is missing, not look empty.

    `null` plus a name in `incomplete` is distinguishable from "you had no
    streaks"; an empty list is not.
    """
    service = _make_service(mock_db)
    service.streakRepository.findAllByOwnerId.side_effect = Exception("boom")

    export = service.exportFor("uid-001")

    assert export["streaks"] is None
    assert export["incomplete"] == ["streaks"]
    assert export["profile"]["username"] == "someone"


def test_timestamps_are_marked_utc(mock_db):
    """Stored instants are naive UTC; printed without the Z they read as local."""
    service = _make_service(mock_db)

    export = service.exportFor("uid-001")

    assert export["profile"]["created_at"].endswith("Z")
    # A date has no time zone to state.
    assert export["profile"]["birth_date"] == "1990-06-15"


# ── what is in it ─────────────────────────────────────────────────────────────

def test_conversations_carry_both_sides(mock_db):
    """A thread with one side removed is not a record of a conversation, and
    the user read the other person's messages when they arrived."""
    service = _make_service(mock_db)
    chat = MagicMock(id="chat-1", sender="uid-001", reciver="uid-002")
    chat.started_at = datetime(2026, 2, 1)
    chat.ended_at = None
    chat.status = 1
    service.chatRepository.findByParticipant.return_value = [chat]
    service.messageRepository.findByChatId.return_value = [
        _mock_message("uid-001", "mine", "msg-1"),
        _mock_message("uid-002", "theirs", "msg-2"),
    ]

    messages = service.exportFor("uid-001")["conversations"][0]["messages"]

    assert [m["body"] for m in messages] == ["mine", "theirs"]
    assert [m["from_me"] for m in messages] == [True, False]


def test_friendship_direction_survives_which_side_the_account_was_on(mock_db):
    service = _make_service(mock_db)
    service.friendshipRepository.findAllByUserId.return_value = [
        MagicMock(id="f-1", sender="uid-001", reciver="uid-002", status=5,
                  created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1)),
        MagicMock(id="f-2", sender="uid-003", reciver="uid-001", status=5,
                  created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1)),
    ]

    friendships = service.exportFor("uid-001")["friendships"]

    assert friendships[0]["direction"] == "sent"
    assert friendships[0]["other_user_id"] == "uid-002"
    assert friendships[1]["direction"] == "received"
    assert friendships[1]["other_user_id"] == "uid-003"


def test_a_missing_badge_row_does_not_lose_the_grant(mock_db):
    service = _make_service(mock_db)
    service.userBadgesRepository.findByUserId.return_value = [
        MagicMock(badge_id="badge-1", given_at=datetime(2026, 3, 1), status=1)
    ]
    service.badgeRepository.findById.side_effect = NoHarmException(statusCode=404, message="gone")

    badges = service.exportFor("uid-001")["badges"]

    assert len(badges) == 1
    assert badges[0]["badge_id"] == "badge-1"
    assert badges[0]["name"] is None


# ── what is deliberately absent ───────────────────────────────────────────────

def test_push_tokens_never_appear(mock_db):
    """A token is a credential for the device holding it, and this file is
    about to be downloaded and probably emailed somewhere."""
    service = _make_service(mock_db)
    service.notificationRepository.findActiveByUserId.return_value = [
        "fcm-token-aaa", "fcm-token-bbb"
    ]

    export = service.exportFor("uid-001")

    assert export["devices"]["active_registrations"] == 2
    assert "fcm-token-aaa" not in str(export)


def test_reports_filed_do_not_name_the_person_reported(mock_db):
    """The reporter's own words are their data; the accusation tied to a name
    is a liability the moment the file leaves the device."""
    service = _make_service(mock_db)
    service.reportRepository.findByReporter.return_value = [
        MagicMock(id="rep-1", reason="harassment", details="they kept messaging me",
                  status=4, created_at=datetime(2026, 4, 1),
                  reported="uid-999", reported_uid="uid-999",
                  reported_username="the-other-account")
    ]

    export = service.exportFor("uid-001")
    filed = export["reports_filed"][0]

    assert filed["details"] == "they kept messaging me"
    assert "reported_username" not in filed
    assert "uid-999" not in str(export)
    assert "the-other-account" not in str(export)


def test_nothing_reads_reports_filed_about_this_account(mock_db):
    """The promise that a reported user is never told who complained is what
    makes reporting usable, and an export is a bad place to break it."""
    service = _make_service(mock_db)

    service.exportFor("uid-001")

    service.reportRepository.findByReporter.assert_called_once_with("uid-001")
    # There is no call that would find reports naming this account.
    assert not service.reportRepository.findAll.called
    assert not service.reportRepository.countByReported.called


def test_notices_do_not_name_the_moderator(mock_db):
    service = _make_service(mock_db)
    service.noticeRepository.findByUser.return_value = [
        MagicMock(kind="warning", reason="harassment", message="please stop",
                  issued_by="uid-moderator", acknowledged_at=None,
                  created_at=datetime(2026, 5, 1))
    ]

    export = service.exportFor("uid-001")

    assert export["moderation_notices"][0]["reason"] == "harassment"
    assert "uid-moderator" not in str(export)
