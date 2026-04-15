"""Unit tests for StreakService."""

import pytest
from unittest.mock import MagicMock, call
from datetime import datetime, timedelta

from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.streakService import StreakService
    service = StreakService(mock_db)
    service.streakRepository = MagicMock()
    service.auditRepository = MagicMock()
    service.userBadgesRepository = MagicMock()
    return service


def _mock_streak(owner_id="uid-001", updated_at=None, start=None, end=None, status=1, is_record=False):
    s = MagicMock()
    s.id = "streak-001"
    s.owner_id = owner_id
    s.updated_at = updated_at or datetime.utcnow()
    s.start = start or (datetime.utcnow() - timedelta(days=2))
    s.end = end
    s.status = status
    s.is_record = is_record
    return s


# ── getCurrentByUserId ────────────────────────────────────────────────────────

def test_getCurrentByUserId_active_streak_returned(mock_db):
    service = _make_service(mock_db)
    streak = _mock_streak(updated_at=datetime.utcnow() - timedelta(hours=1))
    service.streakRepository.findCurrentStreak.return_value = streak

    result = service.getCurrentByUserId("uid-001")
    assert result is streak


def test_getCurrentByUserId_expired_calls_expireAndReset(mock_db):
    """Streak inactive >24h triggers close-and-reset, returns new streak."""
    service = _make_service(mock_db)
    old_streak = _mock_streak(updated_at=datetime.utcnow() - timedelta(hours=25))
    new_streak = _mock_streak(start=datetime.utcnow())

    service.streakRepository.findCurrentStreak.return_value = old_streak
    # findCurrentRecord called inside _closeAndReset
    service.streakRepository.findCurrentRecord.side_effect = NoHarmException(statusCode=404)
    service.streakRepository.create.return_value = new_streak

    result = service.getCurrentByUserId("uid-001")

    # Should have closed old streak and created new one
    service.streakRepository.updateEnd.assert_called_once()
    service.streakRepository.create.assert_called_once()
    assert result is new_streak


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
    old = _mock_streak(start=datetime.utcnow() - timedelta(days=3))
    new = _mock_streak(start=datetime.utcnow())

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
    old = _mock_streak(start=datetime.utcnow() - timedelta(days=10))
    old.id = "old-streak"
    record = _mock_streak(start=datetime.utcnow() - timedelta(days=3))
    record.id = "record-streak"
    record.end = datetime.utcnow() - timedelta(days=1)
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

    result = service.checkin("uid-001")

    assert result is streak
    service.streakRepository.session.commit.assert_called_once()


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
    streak.start = datetime(2024, 1, 1)
    streak.end = datetime(2024, 1, 4)
    duration = service._durationDays(streak)
    assert abs(duration - 3.0) < 0.01


def test_durationDays_no_start_returns_zero(mock_db):
    service = _make_service(mock_db)
    streak = MagicMock()
    streak.start = None
    streak.end = None
    assert service._durationDays(streak) == 0


def test_durationDays_no_end_uses_now(mock_db):
    service = _make_service(mock_db)
    streak = MagicMock()
    streak.start = datetime.utcnow() - timedelta(days=5)
    streak.end = None
    duration = service._durationDays(streak)
    assert 4.9 < duration < 5.1
