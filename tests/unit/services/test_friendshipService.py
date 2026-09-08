"""Unit tests for FriendshipService."""

import pytest
from unittest.mock import MagicMock

from core.config import config
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.friendshipService import FriendshipService
    service = FriendshipService(mock_db)
    service.friendshipRepository = MagicMock()
    return service


def _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=None):
    f = MagicMock()
    f.id = "friendship-001"
    f.sender = sender
    f.reciver = reciver
    f.status = config.STATUS_CODES["pending"] if status is None else status
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
    existing = _mock_friendship(status=config.STATUS_CODES["pending"])
    service.friendshipRepository.findByUsers.return_value = existing

    with pytest.raises(NoHarmException) as exc:
        service.sendRequest("uid-sender", "uid-receiver")
    assert exc.value.statusCode == 409


def test_sendRequest_blocked_relationship_raises_403(mock_db):
    service = _make_service(mock_db)
    existing = _mock_friendship(status=config.STATUS_CODES["blocked"])
    service.friendshipRepository.findByUsers.return_value = existing

    with pytest.raises(NoHarmException) as exc:
        service.sendRequest("uid-sender", "uid-receiver")
    assert exc.value.statusCode == 403


def test_sendRequest_accepted_friendship_raises_409(mock_db):
    service = _make_service(mock_db)
    existing = _mock_friendship(status=config.STATUS_CODES["accepted"])
    service.friendshipRepository.findByUsers.return_value = existing

    with pytest.raises(NoHarmException) as exc:
        service.sendRequest("uid-sender", "uid-receiver")
    assert exc.value.statusCode == 409


# ── accept ────────────────────────────────────────────────────────────────────

def test_accept_by_receiver_succeeds(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=config.STATUS_CODES["pending"])
    service.friendshipRepository.findById.return_value = friendship

    service.accept("friendship-001", "uid-receiver")
    service.friendshipRepository.updateStatus.assert_called_once_with("friendship-001", "accepted")


def test_accept_by_sender_raises_403(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=config.STATUS_CODES["pending"])
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.accept("friendship-001", "uid-sender")
    assert exc.value.statusCode == 403


def test_accept_non_pending_raises_400(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(status=config.STATUS_CODES["accepted"])
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.accept("friendship-001", "uid-receiver")
    assert exc.value.statusCode == 400


# ── reject ────────────────────────────────────────────────────────────────────

def test_reject_by_receiver_calls_update(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=config.STATUS_CODES["pending"])
    service.friendshipRepository.findById.return_value = friendship
    service.friendshipRepository.updateStatus.return_value = MagicMock()

    service.reject("friendship-001", "uid-receiver")
    service.friendshipRepository.updateStatus.assert_called_once_with("friendship-001", "ignored")


def test_reject_by_sender_raises_403(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=config.STATUS_CODES["pending"])
    service.friendshipRepository.findById.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.reject("friendship-001", "uid-sender")
    assert exc.value.statusCode == 403


def test_reject_non_pending_raises_400(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(status=config.STATUS_CODES["accepted"])
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
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=config.STATUS_CODES["blocked"])
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


# ── notification ──────────────────────────────────────────────────────────────
#
# These events used to be emitted by Socket.IO handlers that read the target's
# id straight off the client payload and checked nothing: no friendship, no
# participation, no block. Any authenticated account could push at any user id
# it could name. The handlers are gone and the service emits instead — so what
# has to be tested is not only that the notification fires, but that it cannot
# fire on a path that raised.

@pytest.fixture
def notifications(monkeypatch):
    """Capture what the service publishes, without a loop or Firebase."""
    from domain.services import friendshipService as module

    emitter = MagicMock()
    fcm = MagicMock()
    monkeypatch.setattr(module, "emitter", emitter)
    monkeypatch.setattr(module, "fcmService", fcm)
    return emitter, fcm


def test_sendRequest_notifies_the_receiver(mock_db, notifications):
    emitter, fcm = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findByUsers.side_effect = NoHarmException(statusCode=404)
    service.friendshipRepository.create.return_value = _mock_friendship()

    service.sendRequest("uid-sender", "uid-receiver")

    emitter.notifyFriendship.assert_called_once_with("friend_request", "uid-sender", "uid-receiver")
    assert fcm.sendPushToUser.call_args[0][0] == "uid-receiver"


def test_sendRequest_to_a_blocked_user_notifies_nobody(mock_db, notifications):
    """The push that a block has to stop. Emitting before the 403 is exactly
    what the deleted handler did."""
    emitter, fcm = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findByUsers.return_value = _mock_friendship(
        status=config.STATUS_CODES["blocked"]
    )

    with pytest.raises(NoHarmException):
        service.sendRequest("uid-sender", "uid-receiver")

    emitter.notifyFriendship.assert_not_called()
    fcm.sendPushToUser.assert_not_called()


def test_sendRequest_duplicate_notifies_nobody(mock_db, notifications):
    """Otherwise re-sending is an unlimited push channel at one user."""
    emitter, fcm = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findByUsers.return_value = _mock_friendship()

    with pytest.raises(NoHarmException):
        service.sendRequest("uid-sender", "uid-receiver")

    emitter.notifyFriendship.assert_not_called()
    fcm.sendPushToUser.assert_not_called()


def test_accept_notifies_the_sender(mock_db, notifications):
    emitter, fcm = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship()

    service.accept("friendship-001", "uid-receiver")

    emitter.notifyFriendship.assert_called_once_with("friend_accept", "uid-receiver", "uid-sender")
    assert fcm.sendPushToUser.call_args[0][0] == "uid-sender"


def test_accept_by_a_non_participant_notifies_nobody(mock_db, notifications):
    emitter, fcm = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship()

    with pytest.raises(NoHarmException):
        service.accept("friendship-001", "uid-intruder")

    emitter.notifyFriendship.assert_not_called()
    fcm.sendPushToUser.assert_not_called()


def test_reject_notifies_the_sender_without_a_push(mock_db, notifications):
    emitter, fcm = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship()

    service.reject("friendship-001", "uid-receiver")

    emitter.notifyFriendship.assert_called_once_with("friend_reject", "uid-receiver", "uid-sender")
    fcm.sendPushToUser.assert_not_called()


@pytest.mark.parametrize("actor, peer", [("uid-sender", "uid-receiver"), ("uid-receiver", "uid-sender")])
def test_block_notifies_the_other_participant(mock_db, notifications, actor, peer):
    """Either participant may block, so the target is whichever one did not."""
    emitter, _ = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship()

    service.block("friendship-001", actor)

    emitter.notifyFriendship.assert_called_once_with("friend_block", actor, peer)


def test_block_by_a_non_participant_notifies_nobody(mock_db, notifications):
    emitter, _ = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship()

    with pytest.raises(NoHarmException):
        service.block("friendship-001", "uid-intruder")

    emitter.notifyFriendship.assert_not_called()


def test_unblock_notifies_the_other_participant(mock_db, notifications):
    emitter, _ = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship(
        status=config.STATUS_CODES["blocked"]
    )

    service.unblock("friendship-001", "uid-sender")

    emitter.notifyFriendship.assert_called_once_with("friend_unblock", "uid-sender", "uid-receiver")


def test_delete_notifies_the_peer_captured_before_the_delete(mock_db, notifications):
    emitter, _ = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship()

    service.delete("friendship-001", "uid-sender")

    emitter.notifyFriendship.assert_called_once_with("friend_remove", "uid-sender", "uid-receiver")


def test_delete_by_a_non_participant_notifies_nobody(mock_db, notifications):
    emitter, _ = notifications
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship()

    with pytest.raises(NoHarmException):
        service.delete("friendship-001", "uid-intruder")

    emitter.notifyFriendship.assert_not_called()
