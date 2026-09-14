"""Unit tests for UserService."""

import pytest
from unittest.mock import MagicMock

from core.config import config
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.userService import UserService
    service = UserService(mock_db)
    service.userRepository = MagicMock()
    service.friendshipRepository = MagicMock()
    service.auditRepository = MagicMock()
    return service


# ── findById ──────────────────────────────────────────────────────────────────

def test_findById_returns_user(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = mock_user

    result = service.findById("user-uid-001")
    assert result is mock_user


def test_findById_not_found_propagates_exception(mock_db):
    service = _make_service(mock_db)
    service.userRepository.findById.side_effect = NoHarmException(statusCode=404)

    with pytest.raises(NoHarmException) as exc:
        service.findById("nonexistent")
    assert exc.value.statusCode == 404


# ── findByEmail ───────────────────────────────────────────────────────────────

def test_findByEmail_returns_user(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findByEmail.return_value = mock_user

    result = service.findByEmail("test@example.com")
    assert result is mock_user


# ── getProfile ────────────────────────────────────────────────────────────────

def test_getProfile_returns_own_user(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = mock_user

    result = service.getProfile("user-uid-001")
    assert result is mock_user


# ── getPublicProfile ──────────────────────────────────────────────────────────

def test_getPublicProfile_own_profile_always_accessible(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = mock_user

    result = service.getPublicProfile("user-uid-001", "user-uid-001")
    assert result is mock_user
    # Friendship not checked for own profile
    service.friendshipRepository.findByUsers.assert_not_called()


def test_getPublicProfile_blocked_raises_403(mock_db, mock_user):
    service = _make_service(mock_db)
    mock_friendship = MagicMock()
    mock_friendship.status = config.STATUS_CODES["blocked"]
    service.friendshipRepository.findByUsers.return_value = mock_friendship

    with pytest.raises(NoHarmException) as exc:
        service.getPublicProfile("requester-id", "target-id")
    assert exc.value.statusCode == 403


def test_getPublicProfile_no_friendship_allows_access(mock_db, mock_user):
    service = _make_service(mock_db)
    service.friendshipRepository.findByUsers.side_effect = NoHarmException(statusCode=404)
    service.userRepository.findById.return_value = mock_user

    result = service.getPublicProfile("requester-id", "target-id")
    assert result is mock_user


def test_getPublicProfile_accepted_friendship_allows_access(mock_db, mock_user):
    service = _make_service(mock_db)
    mock_friendship = MagicMock()
    mock_friendship.status = config.STATUS_CODES["accepted"]
    service.friendshipRepository.findByUsers.return_value = mock_friendship
    service.userRepository.findById.return_value = mock_user

    result = service.getPublicProfile("requester-id", "target-id")
    assert result is mock_user


# ── updateProfile ─────────────────────────────────────────────────────────────

def test_updateProfile_success_returns_user(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = mock_user
    # Username is free — findByUsername signals that with a 404.
    service.userRepository.findByUsername.side_effect = NoHarmException(statusCode=404)
    service.userRepository._toEntity.return_value = mock_user

    result = service.updateProfile("user-uid-001", username="newname", profilePicture=None)
    assert result is mock_user
    assert mock_user.username == "newname"
    service.userRepository.session.commit.assert_called_once()


def test_updateProfile_duplicate_username_raises_409(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = mock_user
    other = MagicMock()
    other.id = "someone-else"
    service.userRepository.findByUsername.return_value = other

    with pytest.raises(NoHarmException) as exc:
        service.updateProfile("user-uid-001", username="newname", profilePicture=None)
    assert exc.value.statusCode == 409


def test_updateProfile_invalid_username_raises_400(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = mock_user

    with pytest.raises(NoHarmException) as exc:
        service.updateProfile("user-uid-001", username="x!", profilePicture=None)
    assert exc.value.statusCode == 400


def test_updateProfile_no_username_keeps_original(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = mock_user
    original_username = mock_user.username

    service.updateProfile("user-uid-001", username=None, profilePicture=None)
    assert mock_user.username == original_username


def test_updateProfile_updates_picture(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = mock_user

    new_pic = b"new-picture-bytes"
    service.updateProfile("user-uid-001", username=None, profilePicture=new_pic)
    assert mock_user.profile_picture == new_pic


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_own_account_succeeds(mock_db):
    service = _make_service(mock_db)
    service.userRepository.softDelete.return_value = True

    result = service.delete("uid-001", "uid-001")
    assert result is True
    service.userRepository.softDelete.assert_called_once_with("uid-001")


def test_delete_other_account_raises_403(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.delete("uid-target", "uid-requester")
    assert exc.value.statusCode == 403


# ── updateStatus ─────────────────────────────────────────────────────────────

def test_updateStatus_calls_repo_and_returns_user(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.updateStatus.return_value = mock_user

    result = service.updateStatus("uid-001", status=config.STATUS_CODES["disabled"])
    assert result is mock_user
    service.userRepository.updateStatus.assert_called_once_with("uid-001", config.STATUS_CODES["disabled"])


# ── suspension ────────────────────────────────────────────────────────────────

from datetime import datetime, timedelta, timezone  # noqa: E402


def test_suspend_bans_until_a_date(mock_db):
    service = _make_service(mock_db)

    service.suspend("uid-bad", 3, "uid-admin")

    userId, until = service.userRepository.suspend.call_args[0]
    assert userId == "uid-bad"
    # Three days out, give or take the time the test took — measured in naive
    # UTC, which is what the column holds.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assert timedelta(days=2, hours=23) < (until - now) <= timedelta(days=3)


def test_suspend_with_no_days_is_a_permanent_ban(mock_db):
    """`days: null` has to be written out — a missing field must not mean
    'for ever' by accident."""
    service = _make_service(mock_db)

    service.suspend("uid-bad", None, "uid-admin")

    _, until = service.userRepository.suspend.call_args[0]
    assert until is None


def test_suspend_beyond_the_cap_is_refused(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.suspend("uid-bad", config.MAX_SUSPENSION_DAYS + 1, "uid-admin")

    assert exc.value.statusCode == 400
    assert exc.value.errorCode == "INVALID_SUSPENSION"
    service.userRepository.suspend.assert_not_called()


def test_suspend_for_zero_days_is_refused(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException):
        service.suspend("uid-bad", 0, "uid-admin")
    service.userRepository.suspend.assert_not_called()


def test_a_moderator_cannot_suspend_themselves(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.suspend("uid-admin", 7, "uid-admin")

    assert exc.value.errorCode == "SELF_SUSPENSION"
    service.userRepository.suspend.assert_not_called()


def test_suspend_writes_an_audit_entry_naming_the_moderator(mock_db):
    service = _make_service(mock_db)

    service.suspend("uid-bad", 7, "uid-admin")

    entry = service.auditRepository.create.call_args[0][0]
    assert entry.type == 5
    assert entry.catalyst_id == "uid-admin"


def test_lifting_an_expired_suspension_is_audited(mock_db):
    service = _make_service(mock_db)
    service.userRepository.liftExpiredSuspension.return_value = MagicMock()

    service.liftExpiredSuspension("uid-bad")
    assert service.auditRepository.create.called


def test_lifting_nothing_writes_nothing(mock_db):
    service = _make_service(mock_db)
    service.userRepository.liftExpiredSuspension.return_value = None

    assert service.liftExpiredSuspension("uid-bad") is None
    service.auditRepository.create.assert_not_called()
