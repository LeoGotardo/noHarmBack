"""Unit tests for FriendshipService."""

import pytest
from unittest.mock import MagicMock

from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.friendshipService import FriendshipService
    service = FriendshipService(mock_db)
    service.friendshipRepository = MagicMock()
    return service


def _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=4):
    f = MagicMock()
    f.id = "friendship-001"
    f.sender = sender
    f.reciver = reciver
    f.status = status
    return f


# ── sendRequest ───────────────────────────────────────────────────────────────

def test_sendRequest_success_creates_friendship(mock_db):
    service = _make_service(mock_db)
    service.friendshipRepository.findByUsers.side_effect = NoHarmException(statusCode=404)
    new_friendship = _mock_friendship()
    service.friendshipRepository.create.return_value = new_friendship

    result = service.sendRequest("uid-sender", "uid-receiver")
    assert result is new_friendship
    service.friendshipRepository.create.assert_called_once()


def test_sendRequest_self_raises_400(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.sendRequest("uid-001", "uid-001")
    assert exc.value.statusCode == 400


def test_sendRequest_duplicate_active_raises_409(mock_db):
    service = _make_service(mock_db)
    existing = _mock_friendship(status=4)  # pending
    service.friendshipRepository.findByUsers.return_value = existing

    with pytest.raises(NoHarmException) as exc:
        service.sendRequest("uid-sender", "uid-receiver")
    assert exc.value.statusCode == 409


def test_sendRequest_blocked_relationship_raises_403(mock_db):
    service = _make_service(mock_db)
    existing = _mock_friendship(status=3)  # blocked
    service.friendshipRepository.findByUsers.return_value = existing

    with pytest.raises(NoHarmException) as exc:
        service.sendRequest("uid-sender", "uid-receiver")
    assert exc.value.statusCode == 403


def test_sendRequest_accepted_friendship_raises_409(mock_db):
    service = _make_service(mock_db)
    existing = _mock_friendship(status=5)  # accepted
    service.friendshipRepository.findByUsers.return_value = existing

    with pytest.raises(NoHarmException) as exc:
        service.sendRequest("uid-sender", "uid-receiver")
    assert exc.value.statusCode == 409


# ── accept ────────────────────────────────────────────────────────────────────

def test_accept_by_receiver_succeeds(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=4)
    service.friendshipRepository.findById.return_value = friendship

    result = service.accept("friendship-001", "uid-receiver")
    assert friendship.status == 5  # accepted
    service.friendshipRepository.session.commit.assert_called_once()


def test_accept_by_sender_raises_403(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=4)
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.accept("friendship-001", "uid-sender")
    assert exc.value.statusCode == 403


def test_accept_non_pending_raises_400(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(status=5)  # already accepted
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.accept("friendship-001", "uid-receiver")
    assert exc.value.statusCode == 400


# ── reject ────────────────────────────────────────────────────────────────────

def test_reject_by_receiver_calls_update(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=4)
    service.friendshipRepository.findById.return_value = friendship
    service.friendshipRepository.updateStatus.return_value = MagicMock()

    service.reject("friendship-001", "uid-receiver")
    service.friendshipRepository.updateStatus.assert_called_once_with("friendship-001", "ignored")


def test_reject_by_sender_raises_403(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=4)
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.reject("friendship-001", "uid-sender")
    assert exc.value.statusCode == 403


def test_reject_non_pending_raises_400(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(status=5)  # accepted
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.reject("friendship-001", "uid-receiver")
    assert exc.value.statusCode == 400


# ── block ─────────────────────────────────────────────────────────────────────

def test_block_by_sender_succeeds(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver")
    service.friendshipRepository.findById.return_value = friendship
    service.friendshipRepository.updateStatus.return_value = MagicMock()

    service.block("friendship-001", "uid-sender")
    service.friendshipRepository.updateStatus.assert_called_once_with("friendship-001", "blocked")


def test_block_by_receiver_succeeds(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver")
    service.friendshipRepository.findById.return_value = friendship
    service.friendshipRepository.updateStatus.return_value = MagicMock()

    service.block("friendship-001", "uid-receiver")
    service.friendshipRepository.updateStatus.assert_called_once()


def test_block_by_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver")
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.block("friendship-001", "uid-stranger")
    assert exc.value.statusCode == 403


# ── unblock ───────────────────────────────────────────────────────────────────

def test_unblock_by_participant_restores_disabled(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=3)
    service.friendshipRepository.findById.return_value = friendship
    service.friendshipRepository.updateStatus.return_value = MagicMock()

    service.unblock("friendship-001", "uid-sender")
    service.friendshipRepository.updateStatus.assert_called_once_with("friendship-001", "disabled")


def test_unblock_by_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver")
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.unblock("friendship-001", "uid-stranger")
    assert exc.value.statusCode == 403


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_by_sender_succeeds(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver")
    service.friendshipRepository.findById.return_value = friendship
    service.friendshipRepository.softDelete.return_value = True

    result = service.delete("friendship-001", "uid-sender")
    assert result is True


def test_delete_by_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver")
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.delete("friendship-001", "uid-stranger")
    assert exc.value.statusCode == 403
