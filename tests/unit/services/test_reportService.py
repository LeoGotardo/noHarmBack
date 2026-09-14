"""Unit tests for ReportService."""

import pytest
from unittest.mock import MagicMock, patch

from datetime import datetime, timedelta, timezone

from core.config import config
from exceptions.baseExceptions import NoHarmException


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_service(mock_db):
    from domain.services.reportService import ReportService
    service = ReportService(mock_db)
    service.reportRepository = MagicMock()
    service.evidenceRepository = MagicMock()
    service.chatRepository = MagicMock()
    service.messageRepository = MagicMock()
    service.userRepository = MagicMock()
    service.auditRepository = MagicMock()
    # The clean slate the abuse ceilings see: nothing filed about this pair
    # before, no backlog. Tests that care set their own.
    service.reportRepository.findRecentByPair.return_value = None
    service.reportRepository.countByReporter.return_value = 0
    service.userRepository.findById.return_value = _mock_user()
    service.messageRepository.findRecentByChatId.return_value = []
    return service


@pytest.fixture(autouse=True)
def allow_quota():
    """Let the per-reporter quota through unless a test says otherwise.

    Patched rather than left to the real limiter: without Redis it fails open
    and would pass anyway, but then the suite would silently stop covering the
    check the day Redis is reachable from a test runner.
    """
    with patch("domain.services.reportService._reportLimiter") as limiter:
        limiter.check.return_value = (True, None)
        yield limiter


def _mock_user(status=None):
    u = MagicMock()
    u.id = "uid-reported"
    # Real values, not mocks: the profile snapshot is JSON-serialised, and a
    # MagicMock here would exercise the failure path instead of the normal one.
    u.username = "reported_user"
    u.profile_picture = None
    u.status = config.STATUS_CODES["enabled"] if status is None else status
    return u


def _mock_past_report(status=None, decidedAt=None):
    """This reporter's previous report about the same person.

    Real timestamps, not mocks: the cooldown is arithmetic on `updated_at`.
    """
    r = MagicMock()
    r.id = "report-000"
    r.status = config.STATUS_CODES["pending"] if status is None else status
    r.updated_at = decidedAt
    r.created_at = decidedAt
    return r


def _mock_chat(sender="uid-reporter", reciver="uid-reported"):
    c = MagicMock()
    c.sender = sender
    c.reciver = reciver
    return c


def _mock_message(id="msg-1", sender="uid-reported", text="you should give up"):
    m = MagicMock()
    m.id = id
    m.sender = sender
    m.message = text
    m.send_at = None
    m.created_at = None
    return m


# ── report ────────────────────────────────────────────────────────────────────

def test_report_success_creates_report(mock_db):
    service = _make_service(mock_db)
    created = MagicMock()
    service.reportRepository.create.return_value = created

    result = service.report("uid-reporter", "uid-reported", "harassment", "They keep messaging me.")
    assert result is created
    service.reportRepository.create.assert_called_once()


def test_report_stores_open_status_and_sanitised_details(mock_db):
    service = _make_service(mock_db)

    service.report("uid-reporter", "uid-reported", "spam", "<script>x</script>buy pills")
    filed = service.reportRepository.create.call_args[0][0]

    assert filed.reporter == "uid-reporter"
    assert filed.reported == "uid-reported"
    assert filed.reason == "spam"
    assert filed.status == config.STATUS_CODES["pending"]
    assert "<script>" not in filed.details


def test_report_blank_details_are_stored_as_none(mock_db):
    service = _make_service(mock_db)

    service.report("uid-reporter", "uid-reported", "other", "   ")
    filed = service.reportRepository.create.call_args[0][0]

    assert filed.details is None


def test_report_self_raises_400(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-001", "uid-001", "harassment")
    assert exc.value.statusCode == 400
    assert exc.value.errorCode == "SELF_REPORT"


def test_report_unknown_reason_raises_400(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "because", None)
    assert exc.value.statusCode == 400
    assert exc.value.errorCode == "INVALID_REASON"


def test_report_missing_user_propagates_404(mock_db):
    service = _make_service(mock_db)
    # The reporter's own row is read first (the eligibility check); it is the
    # *reported* lookup that has to 404.
    service.userRepository.findById.side_effect = [
        _mock_user(),
        NoHarmException(statusCode=404, message="User not found"),
    ]

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-gone", "spam")
    assert exc.value.statusCode == 404


def test_report_deleted_account_raises_404(mock_db):
    service = _make_service(mock_db)
    service.userRepository.findById.side_effect = [
        _mock_user(),                                             # the reporter
        _mock_user(status=config.STATUS_CODES["deleted"]),        # the reported user
    ]

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "spam")
    assert exc.value.statusCode == 404


def test_report_duplicate_while_open_raises_409(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findRecentByPair.return_value = _mock_past_report()

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "harassment")
    assert exc.value.statusCode == 409
    assert exc.value.errorCode == "REPORT_ALREADY_OPEN"
    service.reportRepository.create.assert_not_called()


def test_report_after_an_actioned_one_is_allowed_immediately(mock_db):
    """An actioned report is evidence the reporter was right — no cooldown."""
    service = _make_service(mock_db)
    service.reportRepository.findRecentByPair.return_value = _mock_past_report(
        status=config.STATUS_CODES["accepted"],
        decidedAt=_utcnow()
    )

    service.report("uid-reporter", "uid-reported", "harassment")
    service.reportRepository.create.assert_called_once()


def test_report_after_a_recent_dismissal_raises_409(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findRecentByPair.return_value = _mock_past_report(
        status=config.STATUS_CODES["ignored"],
        decidedAt=_utcnow() - timedelta(days=1)
    )

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "harassment")
    assert exc.value.statusCode == 409
    assert exc.value.errorCode == "REPORT_RECENTLY_DISMISSED"
    assert "canReportAgainAt" in (exc.value.details or {})
    service.reportRepository.create.assert_not_called()


def test_report_after_the_dismissal_cooldown_is_allowed(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findRecentByPair.return_value = _mock_past_report(
        status=config.STATUS_CODES["ignored"],
        decidedAt=_utcnow() - timedelta(days=config.REPORT_DISMISSED_COOLDOWN_DAYS + 1)
    )

    service.report("uid-reporter", "uid-reported", "harassment")
    service.reportRepository.create.assert_called_once()


def test_the_dismissal_cooldown_runs_from_the_decision_not_the_filing(mock_db):
    """A report that sat in the queue for weeks must not arrive pre-cooled."""
    service = _make_service(mock_db)
    past = _mock_past_report(
        status=config.STATUS_CODES["ignored"],
        decidedAt=_utcnow() - timedelta(days=1)
    )
    past.created_at = _utcnow() - timedelta(days=config.REPORT_DISMISSED_COOLDOWN_DAYS + 30)
    service.reportRepository.findRecentByPair.return_value = past

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "harassment")
    assert exc.value.errorCode == "REPORT_RECENTLY_DISMISSED"


# ── the per-account ceilings ──────────────────────────────────────────────────

def test_report_over_the_quota_raises_429(mock_db, allow_quota):
    service = _make_service(mock_db)
    allow_quota.check.return_value = (False, "You have filed 10 reports in the last hour.")

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "harassment")
    assert exc.value.statusCode == 429
    assert exc.value.errorCode == "REPORT_QUOTA_EXCEEDED"
    service.reportRepository.create.assert_not_called()


def test_the_quota_is_checked_before_any_database_read(mock_db, allow_quota):
    """The cheapest refusal comes first: an account over its quota costs no query."""
    service = _make_service(mock_db)
    allow_quota.check.return_value = (False, "over quota")

    with pytest.raises(NoHarmException):
        service.report("uid-reporter", "uid-reported", "harassment")
    service.userRepository.findById.assert_not_called()
    service.reportRepository.countByReporter.assert_not_called()


def test_a_filed_report_spends_one_unit_of_quota(mock_db, allow_quota):
    service = _make_service(mock_db)

    service.report("uid-reporter", "uid-reported", "harassment")
    allow_quota.spend.assert_called_once_with("uid-reporter")


def test_a_refused_report_spends_nothing(mock_db, allow_quota):
    """A duplicate is the app's mistake to have allowed, not the user's to pay for."""
    service = _make_service(mock_db)
    service.reportRepository.findRecentByPair.return_value = _mock_past_report()

    with pytest.raises(NoHarmException):
        service.report("uid-reporter", "uid-reported", "harassment")
    allow_quota.spend.assert_not_called()


def test_report_with_a_full_backlog_raises_429(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.countByReporter.return_value = config.REPORT_MAX_OPEN

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "harassment")
    assert exc.value.statusCode == 429
    assert exc.value.errorCode == "TOO_MANY_OPEN_REPORTS"
    service.reportRepository.create.assert_not_called()


def test_the_backlog_cap_counts_only_unreviewed_reports(mock_db):
    service = _make_service(mock_db)

    service.report("uid-reporter", "uid-reported", "harassment")
    service.reportRepository.countByReporter.assert_called_once_with(
        "uid-reporter", config.STATUS_CODES["pending"]
    )


def test_an_unverified_reporter_is_refused(mock_db):
    service = _make_service(mock_db)
    service.userRepository.findById.side_effect = [
        _mock_user(status=config.STATUS_CODES["pending"]),   # the reporter
        _mock_user(),                                        # the reported user
    ]

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "harassment")
    assert exc.value.statusCode == 403
    assert exc.value.errorCode == "REPORTER_NOT_ELIGIBLE"
    service.reportRepository.create.assert_not_called()


def test_a_reporter_whose_row_is_gone_is_refused(mock_db):
    service = _make_service(mock_db)
    service.userRepository.findById.side_effect = NoHarmException(
        statusCode=404, errorCode="USER_NOT_FOUND", message="User not found"
    )

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "harassment")
    assert exc.value.statusCode == 403
    assert exc.value.errorCode == "REPORTER_NOT_ELIGIBLE"


def test_report_writes_an_audit_entry_without_the_free_text(mock_db):
    service = _make_service(mock_db)

    service.report("uid-reporter", "uid-reported", "harassment", "a private description")
    service.auditRepository.create.assert_called_once()


# ── resolve ───────────────────────────────────────────────────────────────────

def _mock_report(status=None, locked_by=None, locked_at=None):
    r = MagicMock()
    r.id = "report-001"
    r.status = config.STATUS_CODES["pending"] if status is None else status
    # Real values, not mocks: the lock is compared against a clock, and a
    # MagicMock there raises instead of exercising the rule.
    r.locked_by = locked_by
    r.locked_at = locked_at
    return r


def test_resolve_accepted_updates_status(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _mock_report()

    service.resolve("report-001", "accepted", "uid-admin")
    service.reportRepository.updateStatus.assert_called_once_with("report-001", "accepted")


def test_resolve_ignored_updates_status(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _mock_report()

    service.resolve("report-001", "ignored", "uid-admin")
    service.reportRepository.updateStatus.assert_called_once_with("report-001", "ignored")


def test_resolve_invalid_status_raises_400(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.resolve("report-001", "banned", "uid-admin")
    assert exc.value.statusCode == 400
    service.reportRepository.updateStatus.assert_not_called()


def test_resolve_already_reviewed_raises_400(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _mock_report(status=config.STATUS_CODES["ignored"])

    with pytest.raises(NoHarmException) as exc:
        service.resolve("report-001", "accepted", "uid-admin")
    assert exc.value.statusCode == 400
    service.reportRepository.updateStatus.assert_not_called()


# ── reads ─────────────────────────────────────────────────────────────────────

def test_getMine_delegates_to_repository(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findByReporter.return_value = []

    assert service.getMine("uid-reporter") == []
    service.reportRepository.findByReporter.assert_called_once_with("uid-reporter", None)


def test_getAll_passes_status_filter(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findAll.return_value = []

    service.getAll(config.STATUS_CODES["pending"])
    service.reportRepository.findAll.assert_called_once_with(config.STATUS_CODES["pending"], None, "newest")


def test_countAgainst_counts_open_reports_by_default(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.countByReported.return_value = 3

    assert service.countAgainst("uid-reported") == 3
    service.reportRepository.countByReported.assert_called_once_with(
        "uid-reported", config.STATUS_CODES["pending"]
    )


# ── evidence capture ──────────────────────────────────────────────────────────

def test_report_captures_the_reported_profile(mock_db):
    """Always, chat or no chat: a username and a picture are what an
    impersonation report *is*, and both can change seconds after it is filed."""
    service = _make_service(mock_db)

    service.report("uid-reporter", "uid-reported", "impersonation")

    captured = service.evidenceRepository.createMany.call_args[0][0]
    assert [item.kind for item in captured] == ["profile"]
    assert "reported_user" in captured[0].content
    assert captured[0].author_id == "uid-reported"


def test_report_with_a_chat_captures_both_sides_of_it(mock_db):
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat()
    service.messageRepository.findRecentByChatId.return_value = [
        _mock_message("m1", "uid-reported", "you should give up"),
        _mock_message("m2", "uid-reporter", "please stop"),
    ]

    service.report("uid-reporter", "uid-reported", "harassment", None, "chat-1")

    captured = service.evidenceRepository.createMany.call_args[0][0]
    assert [item.kind for item in captured] == ["profile", "message", "message"]
    # The reporter's own line is kept too: half a conversation says nothing
    # about whether a message was provocation or reply.
    assert {item.author_id for item in captured[1:]} == {"uid-reported", "uid-reporter"}
    assert [item.content for item in captured[1:]] == ["you should give up", "please stop"]


def test_report_copies_the_messages_rather_than_trusting_the_caller(mock_db):
    """The only thing the caller supplies is an id."""
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat()
    service.messageRepository.findRecentByChatId.return_value = [_mock_message()]

    service.report("uid-reporter", "uid-reported", "harassment", "they said awful things", "chat-1")

    service.messageRepository.findRecentByChatId.assert_called_once()
    captured = service.evidenceRepository.createMany.call_args[0][0]
    contents = [item.content for item in captured if item.kind == "message"]
    assert contents == ["you should give up"]
    # The reporter's prose stays on the report, never in the evidence.
    assert "they said awful things" not in contents


def test_report_on_a_chat_the_reporter_is_not_in_is_403_and_files_nothing(mock_db):
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat(sender="uid-x", reciver="uid-y")

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "harassment", None, "chat-1")

    assert exc.value.statusCode == 403
    assert exc.value.errorCode == "NOT_A_PARTICIPANT"
    # Refused before the row exists: a 403 that still filed a report would make
    # the retry come back 409.
    service.reportRepository.create.assert_not_called()


def test_report_on_a_chat_without_the_reported_user_is_400(mock_db):
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat(reciver="uid-someone-else")

    with pytest.raises(NoHarmException) as exc:
        service.report("uid-reporter", "uid-reported", "harassment", None, "chat-1")

    assert exc.value.statusCode == 400
    assert exc.value.errorCode == "UNRELATED_CHAT"
    service.reportRepository.create.assert_not_called()


def test_a_capture_failure_does_not_fail_the_report(mock_db):
    """A report with no evidence is a weaker record. A report refused because
    the copy broke is no record at all."""
    service = _make_service(mock_db)
    created = MagicMock()
    service.reportRepository.create.return_value = created
    service.evidenceRepository.createMany.side_effect = Exception("db is on fire")

    result = service.report("uid-reporter", "uid-reported", "harassment")

    assert result is created


def test_report_snapshots_the_reported_identity_on_the_row(mock_db):
    service = _make_service(mock_db)

    service.report("uid-reporter", "uid-reported", "spam")
    filed = service.reportRepository.create.call_args[0][0]

    # The foreign key goes NULL when the account is purged; these do not.
    assert filed.reported_uid == "uid-reported"
    assert filed.reported_username == "reported_user"


# ── reading the evidence ──────────────────────────────────────────────────────

def test_get_evidence_returns_the_items_and_logs_who_read_them(mock_db):
    service = _make_service(mock_db)
    report = MagicMock()
    report.id = "report-1"
    service.reportRepository.findById.return_value = report
    service.evidenceRepository.findByReport.return_value = ["item-1", "item-2"]

    result = service.getEvidence("report-1", "uid-admin")

    assert result == ["item-1", "item-2"]
    service.auditRepository.create.assert_called_once()
    entry = service.auditRepository.create.call_args[0][0]
    assert entry.type == 11
    assert entry.catalyst_id == "uid-admin"


def test_get_evidence_for_an_unknown_report_raises(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.side_effect = NoHarmException(
        statusCode=404, errorCode="NOT_FOUND", message="Report not found"
    )

    with pytest.raises(NoHarmException) as exc:
        service.getEvidence("nope", "uid-admin")
    assert exc.value.statusCode == 404


# ── the review lock ───────────────────────────────────────────────────────────

from datetime import datetime, timedelta, timezone  # noqa: E402


def _held(minutes_ago, by="uid-admin"):
    """A report claimed `minutes_ago`, timestamped the way the column is.

    Naive UTC, not local time: the service compares against the same clock, and
    a bare `datetime.now()` here would make every lock look hours old on a
    machine that is not on UTC.
    """
    claimedAt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes_ago)
    return _mock_report(locked_by=by, locked_at=claimedAt)


def test_claim_takes_an_unheld_report(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _mock_report()

    service.claim("report-001", "uid-admin")
    service.reportRepository.claim.assert_called_once_with("report-001", "uid-admin")


def test_claim_is_refused_while_someone_else_holds_it(mock_db):
    """The collision the lock exists for: two moderators reading the same
    conversation and acting on it twice."""
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _held(5, by="uid-other")

    with pytest.raises(NoHarmException) as exc:
        service.claim("report-001", "uid-admin")

    assert exc.value.statusCode == 409
    assert exc.value.errorCode == "REPORT_LOCKED"
    service.reportRepository.claim.assert_not_called()


def test_a_stale_lock_is_no_lock(mock_db):
    """A moderator who closed the tab must not park a report for ever."""
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _held(
        config.REPORT_LOCK_MINUTES + 1, by="uid-other"
    )

    service.claim("report-001", "uid-admin")
    service.reportRepository.claim.assert_called_once_with("report-001", "uid-admin")


def test_reclaiming_your_own_restarts_the_clock(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _held(5, by="uid-admin")

    service.claim("report-001", "uid-admin")
    service.reportRepository.claim.assert_called_once_with("report-001", "uid-admin")


def test_a_reviewed_report_cannot_be_claimed(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _mock_report(
        status=config.STATUS_CODES["accepted"]
    )

    with pytest.raises(NoHarmException) as exc:
        service.claim("report-001", "uid-admin")
    assert exc.value.statusCode == 400


def test_release_drops_your_own_lock(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _held(5, by="uid-admin")

    service.release("report-001", "uid-admin")
    service.reportRepository.releaseLock.assert_called_once_with("report-001")


def test_release_does_not_steal_someone_elses_lock(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _held(5, by="uid-other")

    with pytest.raises(NoHarmException) as exc:
        service.release("report-001", "uid-admin")
    assert exc.value.statusCode == 409
    service.reportRepository.releaseLock.assert_not_called()


def test_resolve_is_refused_while_another_moderator_holds_it(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _held(5, by="uid-other")

    with pytest.raises(NoHarmException) as exc:
        service.resolve("report-001", "accepted", "uid-admin")

    assert exc.value.statusCode == 409
    service.reportRepository.updateStatus.assert_not_called()


def test_resolve_works_on_a_report_you_hold(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _held(5, by="uid-admin")

    service.resolve("report-001", "accepted", "uid-admin")
    service.reportRepository.updateStatus.assert_called_once_with("report-001", "accepted")


def test_resolve_works_without_claiming_first(mock_db):
    """A single moderator never has to think about locks."""
    service = _make_service(mock_db)
    service.reportRepository.findById.return_value = _mock_report()

    service.resolve("report-001", "ignored", "uid-admin")
    service.reportRepository.updateStatus.assert_called_once_with("report-001", "ignored")


# ── the moderation queue's signals ────────────────────────────────────────────

def _mock_queue_report(id="report-1", reporter="uid-reporter", reported="uid-reported"):
    r = MagicMock()
    r.id = id
    r.reporter = reporter
    r.reported_uid = reported
    return r


def test_signalsFor_no_reports_touches_nothing(mock_db):
    service = _make_service(mock_db)

    assert service.signalsFor([]) == {}
    service.reportRepository.standingsByReporters.assert_not_called()
    service.reportRepository.countOpenAgainstMany.assert_not_called()


def test_signalsFor_reads_each_reporter_once_for_the_whole_page(mock_db):
    """One grouped query per page, not one per row."""
    service = _make_service(mock_db)
    service.reportRepository.standingsByReporters.return_value = {}
    service.reportRepository.countOpenAgainstMany.return_value = {}

    service.signalsFor([
        _mock_queue_report("r1", reporter="uid-a"),
        _mock_queue_report("r2", reporter="uid-a"),
        _mock_queue_report("r3", reporter="uid-b"),
    ])

    service.reportRepository.standingsByReporters.assert_called_once()
    asked = service.reportRepository.standingsByReporters.call_args[0][0]
    assert sorted(asked) == ["uid-a", "uid-b"]


def test_signalsFor_reports_the_reporters_history(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.standingsByReporters.return_value = {
        "uid-reporter": {"pending": 1, "accepted": 3, "ignored": 1}
    }
    service.reportRepository.countOpenAgainstMany.return_value = {"uid-reported": 1}

    signals = service.signalsFor([_mock_queue_report()])
    standing = signals["report-1"]["reporter_standing"]

    assert standing["filed"] == 5
    assert standing["accepted"] == 3
    assert standing["ignored"] == 1
    assert standing["pending"] == 1
    # (3 + 1) / (3 + 1 + 2)
    assert standing["weight"] == pytest.approx(4 / 6)


def test_a_first_time_reporter_sits_at_the_midpoint(mock_db):
    """No history is not the same as a bad one — smoothing is what says so."""
    service = _make_service(mock_db)
    service.reportRepository.standingsByReporters.return_value = {
        "uid-reporter": {"pending": 1, "accepted": 0, "ignored": 0}
    }
    service.reportRepository.countOpenAgainstMany.return_value = {}

    signals = service.signalsFor([_mock_queue_report()])
    assert signals["report-1"]["reporter_standing"]["weight"] == pytest.approx(0.5)


def test_a_reporter_who_is_always_dismissed_scores_low(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.standingsByReporters.return_value = {
        "uid-reporter": {"pending": 0, "accepted": 0, "ignored": 10}
    }
    service.reportRepository.countOpenAgainstMany.return_value = {}

    signals = service.signalsFor([_mock_queue_report()])
    assert signals["report-1"]["reporter_standing"]["weight"] < 0.1


def test_a_purged_reporter_has_no_standing_rather_than_a_clean_one(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.standingsByReporters.return_value = {}
    service.reportRepository.countOpenAgainstMany.return_value = {}

    signals = service.signalsFor([_mock_queue_report(reporter=None)])
    assert signals["report-1"]["reporter_standing"] is None


def test_signalsFor_flags_a_pile_up_against_one_account(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.standingsByReporters.return_value = {}
    service.reportRepository.countOpenAgainstMany.return_value = {
        "uid-reported": config.REPORT_BRIGADING_THRESHOLD
    }

    signals = service.signalsFor([_mock_queue_report()])
    assert signals["report-1"]["open_against_reported"] == config.REPORT_BRIGADING_THRESHOLD
    assert signals["report-1"]["looks_coordinated"] is True


def test_signalsFor_does_not_flag_an_ordinary_count(mock_db):
    service = _make_service(mock_db)
    service.reportRepository.standingsByReporters.return_value = {}
    service.reportRepository.countOpenAgainstMany.return_value = {
        "uid-reported": config.REPORT_BRIGADING_THRESHOLD - 1
    }

    signals = service.signalsFor([_mock_queue_report()])
    assert signals["report-1"]["looks_coordinated"] is False


def test_the_coordination_flag_changes_no_account(mock_db):
    """It is a prompt to look. Acting on a count is what a brigade is buying."""
    service = _make_service(mock_db)
    service.reportRepository.standingsByReporters.return_value = {}
    service.reportRepository.countOpenAgainstMany.return_value = {
        "uid-reported": config.REPORT_BRIGADING_THRESHOLD * 3
    }

    service.signalsFor([_mock_queue_report()])
    service.userRepository.updateStatus.assert_not_called()
