"""Unit tests for UserService."""

import pytest
from unittest.mock import MagicMock

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
    mock_friendship.status = 3  # blocked
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
    mock_friendship.status = 5  # accepted
    service.friendshipRepository.findByUsers.return_value = mock_friendship
    service.userRepository.findById.return_value = mock_user

    result = service.getPublicProfile("requester-id", "target-id")
    assert result is mock_user


# ── updateProfile ─────────────────────────────────────────────────────────────

def test_updateProfile_success_returns_user(mock_db, mock_user):
    service = _make_service(mock_db)
    service.userRepository.findById.return_value = mock_user

    result = service.updateProfile("user-uid-001", username="newname", profilePicture=None)
    assert result is mock_user
    assert mock_user.username == "newname"


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

    result = service.updateStatus("uid-001", status=0)
    assert result is mock_user
    service.userRepository.updateStatus.assert_called_once_with("uid-001", 0)
