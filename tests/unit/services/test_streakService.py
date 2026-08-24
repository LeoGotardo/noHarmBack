"""Unit tests for StreakService."""

import pytest
from unittest.mock import MagicMock, call
from datetime import datetime, timedelta, timezone

from core.config import config
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.streakService import StreakService
    service = StreakService(mock_db)
    service.streakRepository = MagicMock()
    service.auditRepository = MagicMock()
    service.userBadgesRepository = MagicMock()
    # badgeRepository used to be left real here. Built on a MagicMock db its
    # findAll() blew up, _checkAndGrantBadges swallowed that and returned, and
    # the entire badge engine sat behind a dead branch in every test that
    # touched a streak mutation. Default: no badges exist, so the granting loop
    # is a no-op unless a test opts in via _with_badges.
    service.badgeRepository = MagicMock()
    service.badgeRepository.findAll.return_value = []
    return service


def _mock_badge(badgeId="badge-1", name="One Week", milestone=7, status=None):
    b = MagicMock()
    b.id = badgeId
    b.name = name
    b.milestone = milestone
    b.status = config.STATUS_CODES["enabled"] if status is None else status
    return b


def _mock_streak(owner_id="uid-001", updated_at=None, start=None, end=None, status=None, is_record=False):
    s = MagicMock()
    s.id = "streak-001"
    s.owner_id = owner_id
    s.updated_at = updated_at or datetime.now(timezone.utc)
    s.start_at = start or (datetime.now(timezone.utc) - timedelta(days=2))
    s.end_at = end
    s.last_checkin = None
    s.status = config.STATUS_CODES["enabled"] if status is None else status
    s.is_record = is_record
    return s


# ── getCurrentByUserId ────────────────────────────────────────────────────────

def test_getCurrentByUserId_active_streak_returned(mock_db):
    service = _make_service(mock_db)
    streak = _mock_streak(updated_at=datetime.now(timezone.utc) - timedelta(hours=1))
    service.streakRepository.findCurrentStreak.return_value = streak

    result = service.getCurrentByUserId("uid-001")
    assert result is streak


def test_getCurrentByUserId_inactive_streak_is_not_expired(mock_db):
    """Inactivity never closes a streak — only an explicit relapse does.

    The 24h auto-expiry was removed on purpose: a streak runs until the user
    reports a relapse via POST /streaks/end.
    """
    service = _make_service(mock_db)
    stale = _mock_streak(updated_at=datetime.now(timezone.utc) - timedelta(hours=25))
    service.streakRepository.findCurrentStreak.return_value = stale

    result = service.getCurrentByUserId("uid-001")

    assert result is stale
    service.streakRepository.updateEnd.assert_not_called()
    service.streakRepository.updateStatus.assert_not_called()
    service.streakRepository.create.assert_not_called()


def test_getCurrentByUserId_no_streak_raises_404(mock_db):
    service = _make_service(mock_db)
    service.streakRepository.findCurrentStreak.side_effect = NoHarmException(statusCode=404)

    with pytest.raises(NoHarmException) as exc:
        service.getCurrentByUserId("uid-001")
    assert exc.value.statusCode == 404


# ── startStreak ───────────────────────────────────────────────────────────────

def test_startStreak_success_creates_streak(mock_db):
    service = _make_service(mock_db)
    service.streakRepository.findCurrentStreak.side_effect = NoHarmException(statusCode=404)
    new_streak = _mock_streak()
    service.streakRepository.create.return_value = new_streak

    result = service.startStreak("uid-001")
    assert result is new_streak
    service.streakRepository.create.assert_called_once()


def test_startStreak_already_active_raises_409(mock_db):
    service = _make_service(mock_db)
    existing = _mock_streak()
    service.streakRepository.findCurrentStreak.return_value = existing

    with pytest.raises(NoHarmException) as exc:
        service.startStreak("uid-001")
    assert exc.value.statusCode == 409


# ── endStreak ─────────────────────────────────────────────────────────────────

def test_endStreak_closes_and_returns_new_streak(mock_db):
    service = _make_service(mock_db)
    old = _mock_streak(start=datetime.now(timezone.utc) - timedelta(days=3))
    new = _mock_streak(start=datetime.now(timezone.utc))

    service.streakRepository.findCurrentStreak.return_value = old
    service.streakRepository.findCurrentRecord.side_effect = NoHarmException(statusCode=404)
    service.streakRepository.create.return_value = new

    result = service.endStreak("uid-001")
    assert result is new
    service.streakRepository.updateEnd.assert_called_once()
    service.streakRepository.updateStatus.assert_called_once()


def test_endStreak_no_active_streak_raises_404(mock_db):
    service = _make_service(mock_db)
    service.streakRepository.findCurrentStreak.side_effect = NoHarmException(statusCode=404)

    with pytest.raises(NoHarmException) as exc:
        service.endStreak("uid-001")
    assert exc.value.statusCode == 404


def test_endStreak_beats_record_marks_as_record(mock_db):
    service = _make_service(mock_db)
    old = _mock_streak(start=datetime.now(timezone.utc) - timedelta(days=10))
    old.id = "old-streak"
    record = _mock_streak(start=datetime.now(timezone.utc) - timedelta(days=3))
    record.id = "record-streak"
    record.end_at = datetime.now(timezone.utc) - timedelta(days=1)
    new = _mock_streak()

    service.streakRepository.findCurrentStreak.return_value = old
    service.streakRepository.findCurrentRecord.return_value = record
    service.streakRepository.create.return_value = new

    service.endStreak("uid-001")
    service.streakRepository.markAsRecord.assert_called_once_with("old-streak")


def test_endStreak_creates_audit_log(mock_db):
    service = _make_service(mock_db)
    old = _mock_streak()
    new = _mock_streak()

    service.streakRepository.findCurrentStreak.return_value = old
    service.streakRepository.findCurrentRecord.side_effect = NoHarmException(statusCode=404)
    service.streakRepository.create.return_value = new

    service.endStreak("uid-001")
    service.auditRepository.create.assert_called_once()


# ── checkin ───────────────────────────────────────────────────────────────────

def test_checkin_updates_timestamp(mock_db):
    service = _make_service(mock_db)
    streak = _mock_streak(owner_id="uid-001")
    service.streakRepository.findCurrentStreak.return_value = streak
    service.streakRepository.updateLastCheckin.return_value = streak

    result = service.checkin("uid-001")

    assert result is streak
    service.streakRepository.updateLastCheckin.assert_called_once()
    assert service.streakRepository.updateLastCheckin.call_args[0][0] == "streak-001"


def test_checkin_no_active_streak_raises_404(mock_db):
    service = _make_service(mock_db)
    service.streakRepository.findCurrentStreak.side_effect = NoHarmException(statusCode=404)

    with pytest.raises(NoHarmException) as exc:
        service.checkin("uid-001")
    assert exc.value.statusCode == 404


def test_checkin_wrong_owner_raises_403(mock_db):
    service = _make_service(mock_db)
    streak = _mock_streak(owner_id="uid-other")
    service.streakRepository.findCurrentStreak.return_value = streak

    with pytest.raises(NoHarmException) as exc:
        service.checkin("uid-001")
    assert exc.value.statusCode == 403


# ── _durationDays ─────────────────────────────────────────────────────────────

def test_durationDays_with_known_dates(mock_db):
    service = _make_service(mock_db)
    streak = MagicMock()
    streak.start_at = datetime(2024, 1, 1)
    streak.end_at = datetime(2024, 1, 4)
    duration = service._durationDays(streak)
    assert abs(duration - 3.0) < 0.01


def test_durationDays_no_start_returns_zero(mock_db):
    service = _make_service(mock_db)
    streak = MagicMock()
    streak.start_at = None
    streak.end_at = None
    assert service._durationDays(streak) == 0


def test_durationDays_no_end_uses_now(mock_db):
    service = _make_service(mock_db)
    streak = MagicMock()
    streak.start_at = datetime.now(timezone.utc) - timedelta(days=5)
    streak.end_at = None
    duration = service._durationDays(streak)
    assert 4.9 < duration < 5.1


# ── _checkAndGrantBadges (§7.1) ───────────────────────────────────────────────
#
# Every one of these was previously unreachable: badgeRepository was left real,
# so findAll() raised, the bare `except Exception: return` caught it, and the
# loop never ran. Mutating the milestone comparison, the already-held guard or
# the disabled-badge guard left the suite fully green.

def _grant_setup(service, streak_days, badges):
    """Point the service at a streak of `streak_days` and a badge catalogue."""
    streak = _mock_streak(start=datetime.now(timezone.utc) - timedelta(days=streak_days))
    service.streakRepository.findCurrentStreak.return_value = streak
    service.badgeRepository.findAll.return_value = badges
    service.userBadgesRepository.existsByUserAndBadge.return_value = False
    return streak


def test_badges_granted_when_milestone_reached(mock_db):
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=10, badges=[_mock_badge("b-7", milestone=7)])

    service._checkAndGrantBadges("uid-001")

    service.userBadgesRepository.grant.assert_called_once()
    userId, badgeId, _ = service.userBadgesRepository.grant.call_args[0]
    assert (userId, badgeId) == ("uid-001", "b-7")


def test_badge_not_granted_below_milestone(mock_db):
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=3, badges=[_mock_badge("b-7", milestone=7)])

    service._checkAndGrantBadges("uid-001")

    service.userBadgesRepository.grant.assert_not_called()


def test_badge_granted_exactly_at_milestone(mock_db):
    """Boundary: `cleanDays < milestone` skips, so an exact hit must grant."""
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=7, badges=[_mock_badge("b-7", milestone=7)])

    service._checkAndGrantBadges("uid-001")

    service.userBadgesRepository.grant.assert_called_once()


def test_only_reached_milestones_are_granted(mock_db):
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=10, badges=[
        _mock_badge("b-1", milestone=1),
        _mock_badge("b-7", milestone=7),
        _mock_badge("b-30", milestone=30),
    ])

    service._checkAndGrantBadges("uid-001")

    granted = {c[0][1] for c in service.userBadgesRepository.grant.call_args_list}
    assert granted == {"b-1", "b-7"}


def test_already_held_badge_is_not_regranted(mock_db):
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=10, badges=[_mock_badge("b-7", milestone=7)])
    service.userBadgesRepository.existsByUserAndBadge.return_value = True

    service._checkAndGrantBadges("uid-001")

    service.userBadgesRepository.grant.assert_not_called()


def test_disabled_badge_is_never_granted(mock_db):
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=100, badges=[
        _mock_badge("b-off", milestone=7, status=config.STATUS_CODES["disabled"]),
    ])

    service._checkAndGrantBadges("uid-001")

    service.userBadgesRepository.grant.assert_not_called()


def test_badge_without_milestone_is_skipped(mock_db):
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=100, badges=[_mock_badge("b-none", milestone=None)])

    service._checkAndGrantBadges("uid-001")

    service.userBadgesRepository.grant.assert_not_called()


def test_grant_writes_audit_log(mock_db):
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=10, badges=[_mock_badge("b-7", milestone=7)])

    service._checkAndGrantBadges("uid-001")

    service.auditRepository.create.assert_called_once()


def test_no_active_streak_grants_nothing(mock_db):
    service = _make_service(mock_db)
    service.streakRepository.findCurrentStreak.side_effect = NoHarmException(statusCode=404)
    service.badgeRepository.findAll.return_value = [_mock_badge(milestone=1)]

    service._checkAndGrantBadges("uid-001")

    service.userBadgesRepository.grant.assert_not_called()


def test_paginated_findAll_is_refused(mock_db):
    """findAll returns a PaginatedResponse when given params, which is not a list.

    Iterating one raises TypeError outside the try block, so the isinstance
    guard is what keeps a paginated catalogue from turning a streak read into a
    500. A MagicMock would not prove this: MagicMock.__iter__ yields nothing.
    """
    from schemas.paginationSchemas import PaginatedResponse

    service = _make_service(mock_db)
    _grant_setup(service, streak_days=10, badges=[_mock_badge(milestone=1)])
    service.badgeRepository.findAll.return_value = PaginatedResponse(
        items=[_mock_badge(milestone=1)], total=1, page=1, pageSize=20,
        totalPages=1, hasNext=False, hasPrevious=False,
    )

    service._checkAndGrantBadges("uid-001")

    service.userBadgesRepository.grant.assert_not_called()


def test_one_failing_grant_does_not_stop_the_others(mock_db):
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=100, badges=[
        _mock_badge("b-1", milestone=1),
        _mock_badge("b-7", milestone=7),
    ])
    service.userBadgesRepository.grant.side_effect = [Exception("write failed"), None]

    service._checkAndGrantBadges("uid-001")

    assert service.userBadgesRepository.grant.call_count == 2


def test_badge_repository_failure_never_breaks_the_streak_call(mock_db):
    """Badge accrual is a side effect of a read — it must not surface as a 500."""
    service = _make_service(mock_db)
    streak = _mock_streak()
    service.streakRepository.findCurrentStreak.return_value = streak
    service.badgeRepository.findAll.side_effect = Exception("db down")

    assert service.getCurrentByUserId("uid-001") is streak


def test_getCurrentByUserId_triggers_badge_check(mock_db):
    """Clean days accrue with wall-clock time, so the common read must grant."""
    service = _make_service(mock_db)
    _grant_setup(service, streak_days=10, badges=[_mock_badge("b-7", milestone=7)])

    service.getCurrentByUserId("uid-001")

    service.userBadgesRepository.grant.assert_called_once()


# ── record handling on reset (§6.2 / §6.4) ────────────────────────────────────

def test_endStreak_shorter_than_record_leaves_record_alone(mock_db):
    service = _make_service(mock_db)
    old = _mock_streak(start=datetime.now(timezone.utc) - timedelta(days=2))
    old.id = "old-streak"
    record = _mock_streak(start=datetime.now(timezone.utc) - timedelta(days=30))
    record.id = "record-streak"
    record.end_at = datetime.now(timezone.utc) - timedelta(days=10)

    service.streakRepository.findCurrentStreak.return_value = old
    service.streakRepository.findCurrentRecord.return_value = record

    service.endStreak("uid-001")

    service.streakRepository.markAsRecord.assert_not_called()
    service.streakRepository.unmarkRecord.assert_not_called()


def test_endStreak_beating_record_unmarks_the_old_one(mock_db):
    """Two rows flagged is_record at once makes /streaks/record ambiguous."""
    service = _make_service(mock_db)
    old = _mock_streak(start=datetime.now(timezone.utc) - timedelta(days=10))
    old.id = "old-streak"
    record = _mock_streak(start=datetime.now(timezone.utc) - timedelta(days=3))
    record.id = "record-streak"
    record.end_at = datetime.now(timezone.utc) - timedelta(days=1)

    service.streakRepository.findCurrentStreak.return_value = old
    service.streakRepository.findCurrentRecord.return_value = record

    service.endStreak("uid-001")

    service.streakRepository.unmarkRecord.assert_called_once_with("record-streak")
    service.streakRepository.markAsRecord.assert_called_once_with("old-streak")


def test_endStreak_no_record_and_zero_duration_marks_nothing(mock_db):
    """A streak started and ended at the same instant is not a record."""
    service = _make_service(mock_db)
    now = datetime.now(timezone.utc)
    old = _mock_streak(start=now)
    old.id = "old-streak"
    service.streakRepository.findCurrentStreak.return_value = old
    service.streakRepository.findCurrentRecord.side_effect = NoHarmException(statusCode=404)

    service.endStreak("uid-001", endAt=now)

    service.streakRepository.markAsRecord.assert_not_called()


def test_endStreak_no_record_marks_first_completed_streak(mock_db):
    service = _make_service(mock_db)
    old = _mock_streak(start=datetime.now(timezone.utc) - timedelta(days=4))
    old.id = "old-streak"
    service.streakRepository.findCurrentStreak.return_value = old
    service.streakRepository.findCurrentRecord.side_effect = NoHarmException(statusCode=404)

    service.endStreak("uid-001")

    service.streakRepository.markAsRecord.assert_called_once_with("old-streak")


def test_endStreak_closes_with_the_requested_end_time(mock_db):
    service = _make_service(mock_db)
    old = _mock_streak(start=datetime(2024, 1, 1, tzinfo=timezone.utc))
    old.id = "old-streak"
    service.streakRepository.findCurrentStreak.return_value = old
    service.streakRepository.findCurrentRecord.side_effect = NoHarmException(statusCode=404)

    endAt = datetime(2024, 1, 11, tzinfo=timezone.utc)
    service.endStreak("uid-001", endAt=endAt)

    service.streakRepository.updateEnd.assert_called_once_with("old-streak", endAt)

    # The replacement streak picks up from the requested end, not from "now".
    # StreakModel is patched by the root conftest, so the kwargs are readable.
    import domain.services.streakService as streakModule
    assert streakModule.StreakModel.call_args.kwargs["start_at"] == endAt


def test_endStreak_disables_the_closed_streak(mock_db):
    service = _make_service(mock_db)
    old = _mock_streak()
    old.id = "old-streak"
    service.streakRepository.findCurrentStreak.return_value = old
    service.streakRepository.findCurrentRecord.side_effect = NoHarmException(statusCode=404)

    service.endStreak("uid-001")

    service.streakRepository.updateStatus.assert_called_once_with(
        "old-streak", config.STATUS_CODES["disabled"]
    )


# ── _asUtc ────────────────────────────────────────────────────────────────────
#
# Encrypted DateTime columns decrypt to naive datetimes while in-process values
# are aware. Subtracting one from the other is a TypeError, which is the whole
# reason this helper exists — but nothing exercised the mixed case.

def test_asUtc_tags_naive_datetime(mock_db):
    service = _make_service(mock_db)
    naive = datetime(2024, 1, 1, 12, 0, 0)
    assert service._asUtc(naive).tzinfo == timezone.utc


def test_asUtc_leaves_aware_datetime_untouched(mock_db):
    service = _make_service(mock_db)
    aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert service._asUtc(aware) is aware


def test_asUtc_passes_none_through(mock_db):
    service = _make_service(mock_db)
    assert service._asUtc(None) is None


def test_durationDays_mixes_naive_start_with_aware_end(mock_db):
    """The regression this helper was written for: naive DB value vs aware now."""
    service = _make_service(mock_db)
    streak = MagicMock()
    # naive, exactly as an encrypted DateTime column decrypts
    streak.start_at = (datetime.now(timezone.utc) - timedelta(days=5)).replace(tzinfo=None)
    streak.end_at = None                                     # → aware now()
    assert 4.9 < service._durationDays(streak) < 5.1


def test_durationDays_negative_range_clamps_to_zero(mock_db):
    service = _make_service(mock_db)
    streak = MagicMock()
    streak.start_at = datetime(2024, 1, 10, tzinfo=timezone.utc)
    streak.end_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert service._durationDays(streak) == 0.0
