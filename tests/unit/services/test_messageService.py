"""Unit tests for MessageService."""

import pytest
from unittest.mock import MagicMock

from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.messageService import MessageService
    service = MessageService(mock_db)
    service.messageRepository = MagicMock()
    service.chatRepository = MagicMock()
    return service


def _mock_chat(sender="uid-sender", reciver="uid-receiver", status=1):
    c = MagicMock()
    c.id = "chat-001"
    c.sender = sender
    c.reciver = reciver
    c.status = status
    return c


def _mock_message(chat_id="chat-001", sender="uid-sender", status=7):
    m = MagicMock()
    m.id = "msg-001"
    m.chat = chat_id
    m.sender = sender
    m.status = status
    return m


# ── sendMessage ───────────────────────────────────────────────────────────────

def test_sendMessage_success_creates_message(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=1)  # enabled
    service.chatRepository.findById.return_value = chat
    new_msg = _mock_message()
    service.messageRepository.create.return_value = new_msg

    result = service.sendMessage("chat-001", "uid-sender", "Hello!")
    assert result is new_msg
    service.messageRepository.create.assert_called_once()


def test_sendMessage_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver", status=1)
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-stranger", "Hi")
    assert exc.value.statusCode == 403


def test_sendMessage_pending_chat_auto_activates(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=4)  # pending
    service.chatRepository.findById.return_value = chat
    service.messageRepository.create.return_value = _mock_message()

    service.sendMessage("chat-001", "uid-sender", "First message")
    service.chatRepository.updateStatus.assert_called_once()


def test_sendMessage_disabled_chat_raises_400(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=0)  # disabled
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-sender", "Hi")
    assert exc.value.statusCode == 400


def test_sendMessage_empty_content_raises_400(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=1)
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-sender", "   ")
    assert exc.value.statusCode == 400


def test_sendMessage_html_content_is_sanitized(mock_db):
    """Script tags are stripped; inner text preserved → MessageModel called with clean content."""
    from unittest.mock import patch as _patch

    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=1)
    service.chatRepository.findById.return_value = chat

    # Patch MessageModel at the service level so we can inspect the kwargs
    with _patch("domain.services.messageService.MessageModel") as MockMsg:
        MockMsg.return_value = MagicMock()
        service.messageRepository.create.return_value = _mock_message()

        service.sendMessage("chat-001", "uid-sender", "<script>evil()</script>hello")

        # bleach strips tags but keeps inner text: "<script>evil()</script>hello" → "evil()hello"
        _, kwargs = MockMsg.call_args
        assert "<script>" not in kwargs["message"]
        assert "hello" in kwargs["message"]


def test_sendMessage_xss_only_content_raises_400(mock_db):
    """After sanitization, if nothing remains → 400. Empty-body tags sanitize to ''."""
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=1)
    service.chatRepository.findById.return_value = chat

    # bleach strips tags + content for empty-body tags: "<b></b>" → ""
    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-sender", "<b></b>")
    assert exc.value.statusCode == 400


# ── markAsRead ────────────────────────────────────────────────────────────────

def test_markAsRead_unread_message_marks_it(mock_db):
    service = _make_service(mock_db)
    msg = _mock_message(status=7)  # unread
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver")
    service.messageRepository.findById.return_value = msg
    service.chatRepository.findById.return_value = chat
    read_msg = _mock_message(status=8)
    service.messageRepository.markAsRead.return_value = read_msg

    result = service.markAsRead("msg-001", "uid-receiver")
    assert result is read_msg
    service.messageRepository.markAsRead.assert_called_once_with("msg-001")


def test_markAsRead_already_read_is_idempotent(mock_db):
    service = _make_service(mock_db)
    msg = _mock_message(status=8)  # already read
    service.messageRepository.findById.return_value = msg

    result = service.markAsRead("msg-001", "uid-receiver")
    assert result is msg
    # Should not call markAsRead again
    service.messageRepository.markAsRead.assert_not_called()


def test_markAsRead_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    msg = _mock_message(status=7)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver")
    service.messageRepository.findById.return_value = msg
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.markAsRead("msg-001", "uid-stranger")
    assert exc.value.statusCode == 403


# ── markAllAsRead ─────────────────────────────────────────────────────────────

def test_markAllAsRead_participant_succeeds(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver")
    service.chatRepository.findById.return_value = chat
    service.messageRepository.markAllAsRead.return_value = True

    result = service.markAllAsRead("chat-001", "uid-receiver")
    assert result is True
    service.messageRepository.markAllAsRead.assert_called_once_with("chat-001")


def test_markAllAsRead_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver")
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.markAllAsRead("chat-001", "uid-stranger")
    assert exc.value.statusCode == 403
