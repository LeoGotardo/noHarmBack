"""Unit tests for ChatService."""

import pytest
from unittest.mock import MagicMock

from core.config import config
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.chatService import ChatService
    service = ChatService(mock_db)
    service.chatRepository = MagicMock()
    service.friendshipRepository = MagicMock()
    return service


def _mock_chat(sender="uid-sender", reciver="uid-receiver", status=None):
    c = MagicMock()
    c.id = "chat-001"
    c.sender = sender
    c.reciver = reciver
    c.status = config.STATUS_CODES["pending"] if status is None else status
    return c


def _mock_friendship(status=None):
    f = MagicMock()
    f.status = config.STATUS_CODES["accepted"] if status is None else status
    return f


# ── getAllByUserId ────────────────────────────────────────────────────────────

def test_getAllByUserId_combines_sent_and_received(mock_db):
    service = _make_service(mock_db)
    sent = [_mock_chat()]
    received = [_mock_chat(sender="uid-other", reciver="uid-001")]
    service.chatRepository.findAllBySenderId.return_value = sent
    service.chatRepository.findAllByReciverId.return_value = received

    result = service.getAllByUserId("uid-001")
    assert len(result) == 2


# ── get ───────────────────────────────────────────────────────────────────────

def test_get_as_participant_returns_chat(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-001")
    service.chatRepository.findById.return_value = chat

    result = service.get("chat-001", "uid-001")
    assert result is chat


def test_get_as_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver")
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.get("chat-001", "uid-stranger")
    assert exc.value.statusCode == 403


# ── getOrCreate ───────────────────────────────────────────────────────────────

def test_getOrCreate_creates_new_chat_when_none_exists(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(status=config.STATUS_CODES["accepted"])
    service.friendshipRepository.findByUsers.return_value = friendship

    # No active chat between users
    service.chatRepository.findAllBySenderId.return_value = []
    service.chatRepository.findAllByReciverId.return_value = []

    new_chat = _mock_chat()
    service.chatRepository.create.return_value = new_chat

    result = service.getOrCreate("uid-sender", "uid-receiver")
    assert result is new_chat
    service.chatRepository.create.assert_called_once()


def test_getOrCreate_returns_existing_active_chat(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(status=config.STATUS_CODES["accepted"])
    service.friendshipRepository.findByUsers.return_value = friendship

    existing = _mock_chat(sender="uid-sender", reciver="uid-receiver", status=config.STATUS_CODES["pending"])
    service.chatRepository.findAllBySenderId.return_value = [existing]

    result = service.getOrCreate("uid-sender", "uid-receiver")
    assert result is existing
    service.chatRepository.create.assert_not_called()


def test_getOrCreate_no_friendship_raises_403(mock_db):
    service = _make_service(mock_db)
    service.friendshipRepository.findByUsers.side_effect = NoHarmException(statusCode=404)

    with pytest.raises(NoHarmException) as exc:
        service.getOrCreate("uid-sender", "uid-receiver")
    assert exc.value.statusCode == 403


def test_getOrCreate_pending_friendship_raises_403(mock_db):
    service = _make_service(mock_db)
    friendship = _mock_friendship(status=config.STATUS_CODES["pending"])
    service.friendshipRepository.findByUsers.return_value = friendship

    with pytest.raises(NoHarmException) as exc:
        service.getOrCreate("uid-sender", "uid-receiver")
    assert exc.value.statusCode == 403


# ── activate ──────────────────────────────────────────────────────────────────

def test_activate_pending_chat_succeeds(mock_db):
    service = _make_service(mock_db)
    pending_chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["pending"])
    active_chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["enabled"])
    service.chatRepository.findById.side_effect = [pending_chat, active_chat]

    result = service.activate("chat-001", "uid-sender")
    service.chatRepository.updateStatus.assert_called_once()
    assert result is active_chat


def test_activate_already_active_raises_400(mock_db):
    service = _make_service(mock_db)
    active_chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["enabled"])
    service.chatRepository.findById.return_value = active_chat

    with pytest.raises(NoHarmException) as exc:
        service.activate("chat-001", "uid-sender")
    assert exc.value.statusCode == 400


def test_activate_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver", status=config.STATUS_CODES["pending"])
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.activate("chat-001", "uid-stranger")
    assert exc.value.statusCode == 403


# ── endChat ───────────────────────────────────────────────────────────────────

def test_endChat_by_participant_closes_chat(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["enabled"])
    ended_chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["disabled"])
    service.chatRepository.findById.side_effect = [chat, ended_chat]

    result = service.endChat("chat-001", "uid-sender")
    service.chatRepository.updateEndedAt.assert_called_once()
    service.chatRepository.updateStatus.assert_called_once()
    assert result is ended_chat


def test_endChat_by_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver")
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.endChat("chat-001", "uid-stranger")
    assert exc.value.statusCode == 403


# ── delete ────────────────────────────────────────────────────────────────────

def test_delete_by_participant_soft_deletes(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender")
    service.chatRepository.findById.return_value = chat
    service.chatRepository.softDelete.return_value = True

    result = service.delete("chat-001", "uid-sender")
    assert result is True


def test_delete_by_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver")
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.delete("chat-001", "uid-stranger")
    assert exc.value.statusCode == 403
