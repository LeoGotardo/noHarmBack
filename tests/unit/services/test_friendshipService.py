"""Unit tests for FriendshipService."""

import pytest
from unittest.mock import MagicMock, patch

from core.config import config
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.friendshipService import FriendshipService
    service = FriendshipService(mock_db)
    service.friendshipRepository = MagicMock()
    return service


def _mock_friendship(sender="uid-sender", reciver="uid-receiver", status=None, blocked_by=None):
    f = MagicMock()
    f.id = "friendship-001"
    f.sender = sender
    f.reciver = reciver
    f.status = config.STATUS_CODES["pending"] if status is None else status
    # Explicit: a MagicMock attribute is never None, and every unblock would
    # read as someone else's block.
    f.blocked_by = blocked_by
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


def test_sendRequest_after_unblock_creates_a_new_request(mock_db):
    """A lifted block leaves the row `disabled`; that is history, not a request.

    It used to answer 409 "already exists" while the app showed the pair as
    strangers with an Add friend button — so after an unblock neither side
    could ever ask again.
    """
    service = _make_service(mock_db)
    existing = _mock_friendship(status=config.STATUS_CODES["disabled"])
    service.friendshipRepository.findByUsers.return_value = existing
    service.friendshipRepository.create.side_effect = lambda model: model

    with patch("domain.services.friendshipService.emitter"), \
         patch("domain.services.friendshipService.fcmService"):
        created = service.sendRequest("uid-sender", "uid-receiver")

    assert created.status == config.STATUS_CODES["pending"]
    service.friendshipRepository.create.assert_called_once()


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
    service.friendshipRepository.setBlocked.return_value = MagicMock()

    service.block("friendship-001", "uid-sender")
    service.friendshipRepository.setBlocked.assert_called_once_with("friendship-001", "uid-sender")


def test_block_by_receiver_succeeds(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(sender="uid-sender", reciver="uid-receiver")
    service.friendshipRepository.findById.return_value = friendship
    service.friendshipRepository.setBlocked.return_value = MagicMock()

    service.block("friendship-001", "uid-receiver")
    service.friendshipRepository.setBlocked.assert_called_once_with("friendship-001", "uid-receiver")


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
    service.friendshipRepository.clearBlock.return_value = MagicMock()

    service.unblock("friendship-001", "uid-sender")
    service.friendshipRepository.clearBlock.assert_called_once_with("friendship-001")


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


# ── blocking by user id, and who may lift a block ─────────────────────────────

def test_the_blocked_side_cannot_unblock(mock_db):
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship(
        status=config.STATUS_CODES["blocked"], blocked_by="uid-sender"
    )

    with pytest.raises(NoHarmException) as exc:
        service.unblock("friendship-001", "uid-receiver")

    assert exc.value.statusCode == 403
    service.friendshipRepository.clearBlock.assert_not_called()


def test_a_legacy_block_with_no_owner_keeps_the_old_rule(mock_db):
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship(
        status=config.STATUS_CODES["blocked"], blocked_by=None
    )

    service.unblock("friendship-001", "uid-receiver")

    service.friendshipRepository.clearBlock.assert_called_once()


def test_blocking_an_already_blocked_row_changes_nothing(mock_db):
    """Re-stamping `blocked_by` would hand the unblock to whoever asked second."""
    service = _make_service(mock_db)
    service.friendshipRepository.findById.return_value = _mock_friendship(
        status=config.STATUS_CODES["blocked"], blocked_by="uid-receiver"
    )

    service.block("friendship-001", "uid-sender")

    service.friendshipRepository.setBlocked.assert_not_called()


def test_blockUser_creates_a_row_for_a_stranger(mock_db):
    service = _make_service(mock_db)
    service.friendshipRepository.findAllBetween.return_value = []

    with patch("domain.services.friendshipService.UserRepository"):
        service.blockUser("uid-a", "uid-b")

    created = service.friendshipRepository.create.call_args[0][0]
    assert created.sender == "uid-a" and created.reciver == "uid-b"
    assert created.status == config.STATUS_CODES["blocked"]
    assert created.blocked_by == "uid-a"


def test_blockUser_moves_the_live_row_not_a_deleted_one(mock_db):
    service = _make_service(mock_db)
    deleted = _mock_friendship(status=config.STATUS_CODES["deleted"])
    deleted.id = "old"
    live = _mock_friendship(status=config.STATUS_CODES["accepted"])
    live.id = "live"
    service.friendshipRepository.findAllBetween.return_value = [deleted, live]

    with patch("domain.services.friendshipService.UserRepository"):
        service.blockUser("uid-sender", "uid-receiver")

    service.friendshipRepository.setBlocked.assert_called_once_with("live", "uid-sender")
    service.friendshipRepository.create.assert_not_called()


def test_blockUser_refuses_yourself(mock_db):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.blockUser("uid-a", "uid-a")

    assert exc.value.errorCode == "SELF_BLOCK"


def test_unblockUser_with_no_block_is_404(mock_db):
    service = _make_service(mock_db)
    service.friendshipRepository.findAllBetween.return_value = [
        _mock_friendship(status=config.STATUS_CODES["accepted"])
    ]

    with pytest.raises(NoHarmException) as exc:
        service.unblockUser("uid-sender", "uid-receiver")

    assert exc.value.statusCode == 404
