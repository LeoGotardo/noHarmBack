"""Unit tests for NoticeService — what moderation says to the user.

The rung this adds is the one that was missing: a warning changes nothing about
the account, which is exactly why a moderator can use it. What these guard is
the two rules that make it safe to send at all — it never names the reporter,
and it is never the answer to a report about someone's safety.
"""

import pytest
from unittest.mock import MagicMock

from core.config import config
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.noticeService import NoticeService
    service = NoticeService(mock_db)
    service.noticeRepository = MagicMock()
    service.userRepository = MagicMock()
    service.auditRepository = MagicMock()
    service.userRepository.findById.return_value = _mock_user()
    return service


def _mock_user(status=None):
    u = MagicMock()
    u.id = "uid-warned"
    u.status = config.STATUS_CODES["enabled"] if status is None else status
    return u


# ── warn ──────────────────────────────────────────────────────────────────────

def test_warn_creates_a_warning_naming_the_conduct(mock_db):
    service = _make_service(mock_db)

    service.warn("uid-warned", "harassment", "uid-admin", "Please stop.")
    issued = service.noticeRepository.create.call_args[0][0]

    assert issued.user_id == "uid-warned"
    assert issued.kind == "warning"
    assert issued.reason == "harassment"
    assert issued.message == "Please stop."
    assert issued.issued_by == "uid-admin"


def test_warn_sanitises_the_moderators_words(mock_db):
    service = _make_service(mock_db)

    service.warn("uid-warned", "spam", "uid-admin", "<script>x</script>stop it")
    issued = service.noticeRepository.create.call_args[0][0]

    assert "<script>" not in issued.message


def test_warn_with_no_message_stores_none(mock_db):
    service = _make_service(mock_db)

    service.warn("uid-warned", "spam", "uid-admin", "   ")
    assert service.noticeRepository.create.call_args[0][0].message is None


def test_a_report_about_someones_safety_is_never_a_warning(mock_db):
    """In a recovery app that report is usually a frightened friend. Answering
    it with a telling-off is the worst available move."""
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.warn("uid-warned", "self_harm", "uid-admin")

    assert exc.value.statusCode == 400
    assert exc.value.errorCode == "NOT_A_WARNING"
    assert "crisis" in exc.value.message.lower()
    service.noticeRepository.create.assert_not_called()


def test_unknown_reason_is_refused(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.warn("uid-warned", "because", "uid-admin")
    assert exc.value.errorCode == "INVALID_REASON"


def test_a_moderator_cannot_warn_themselves(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.warn("uid-admin", "spam", "uid-admin")
    assert exc.value.errorCode == "SELF_NOTICE"


def test_warning_a_deleted_account_is_a_404(mock_db):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = _mock_user(
        status=config.STATUS_CODES["deleted"]
    )

    with pytest.raises(NoHarmException) as exc:
        service.warn("uid-warned", "spam", "uid-admin")
    assert exc.value.statusCode == 404


def test_warn_is_audited_against_the_moderator(mock_db):
    service = _make_service(mock_db)

    service.warn("uid-warned", "harassment", "uid-admin", "the note")
    entry = service.auditRepository.create.call_args[0][0]

    assert entry.type == 12
    assert entry.catalyst_id == "uid-admin"
    # The audit names the conduct, never the moderator's free text.
    assert "the note" not in entry.description


# ── suspension notice ─────────────────────────────────────────────────────────

def test_a_suspension_writes_its_own_notice(mock_db):
    service = _make_service(mock_db)

    service.noticeOfSuspension("uid-warned", "harassment", "uid-admin", "Back in a week.")
    issued = service.noticeRepository.create.call_args[0][0]

    assert issued.kind == "suspension"
    assert issued.message == "Back in a week."


def test_an_unknown_reason_on_a_suspension_notice_degrades_to_other(mock_db):
    """The suspension already happened; a notice is not the place to be strict."""
    service = _make_service(mock_db)

    service.noticeOfSuspension("uid-warned", "whatever", "uid-admin")
    assert service.noticeRepository.create.call_args[0][0].reason == "other"


def test_a_failed_notice_never_undoes_the_suspension(mock_db):
    service = _make_service(mock_db)
    service.noticeRepository.create.side_effect = Exception("db is on fire")

    assert service.noticeOfSuspension("uid-warned", "spam", "uid-admin") is None


# ── acknowledge ───────────────────────────────────────────────────────────────

def test_acknowledge_stamps_your_own_notice(mock_db):
    service = _make_service(mock_db)
    notice = MagicMock()
    notice.user_id = "uid-warned"
    service.noticeRepository.findById.return_value = notice

    service.acknowledge("notice-1", "uid-warned")
    service.noticeRepository.acknowledge.assert_called_once_with("notice-1")


def test_acknowledging_someone_elses_notice_is_a_404(mock_db):
    """404 rather than 403: a notice belonging to someone else is not a thing
    this caller gets told exists."""
    service = _make_service(mock_db)
    notice = MagicMock()
    notice.user_id = "uid-someone-else"
    service.noticeRepository.findById.return_value = notice

    with pytest.raises(NoHarmException) as exc:
        service.acknowledge("notice-1", "uid-warned")

    assert exc.value.statusCode == 404
    service.noticeRepository.acknowledge.assert_not_called()
