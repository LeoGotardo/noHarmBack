"""Unit tests for MessageService."""

import pytest
from unittest.mock import MagicMock

from core.config import config
from exceptions.baseExceptions import NoHarmException


def _make_service(mock_db):
    from domain.services.messageService import MessageService
    service = MessageService(mock_db)
    service.messageRepository = MagicMock()
    service.chatRepository = MagicMock()
    return service


def _mock_chat(sender="uid-sender", reciver="uid-receiver", status=None):
    c = MagicMock()
    c.id = "chat-001"
    c.sender = sender
    c.reciver = reciver
    c.status = config.STATUS_CODES["enabled"] if status is None else status
    return c


def _mock_message(chat_id="chat-001", sender="uid-sender", status=None):
    m = MagicMock()
    m.id = "msg-001"
    m.chat = chat_id
    m.sender = sender
    m.status = config.STATUS_CODES["unread"] if status is None else status
    return m


# ── reads ─────────────────────────────────────────────────────────────────────

def test_getByChatId_participant_gets_the_messages(mock_db):
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat()
    service.messageRepository.findByChatId.return_value = ["msg"]

    assert service.getByChatId("chat-001", "uid-sender") == ["msg"]


def test_getByChatId_non_participant_raises_403(mock_db):
    """RLS used to be the only thing stopping this.

    The route took `currentUserId` and never passed it on, so reading any
    conversation was a matter of holding its id — which the API hands out. The
    `tb_4` policy caught it in production and nothing caught it anywhere else,
    including in a session run by a role that bypasses RLS.
    """
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat()

    with pytest.raises(NoHarmException) as exc:
        service.getByChatId("chat-001", "uid-stranger")

    assert exc.value.statusCode == 403
    service.messageRepository.findByChatId.assert_not_called()


def test_getUnreadByChatId_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat()

    with pytest.raises(NoHarmException) as exc:
        service.getUnreadByChatId("chat-001", "uid-stranger")

    assert exc.value.statusCode == 403
    service.messageRepository.findUnreadByChatId.assert_not_called()


def test_getUnreadByChatId_receiver_is_a_participant(mock_db):
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat()
    service.messageRepository.findUnreadByChatId.return_value = []

    assert service.getUnreadByChatId("chat-001", "uid-receiver") == []


# ── sendMessage ───────────────────────────────────────────────────────────────

def test_sendMessage_success_creates_message(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["enabled"])
    service.chatRepository.findById.return_value = chat
    new_msg = _mock_message()
    service.messageRepository.create.return_value = new_msg

    result = service.sendMessage("chat-001", "uid-sender", "Hello!")
    assert result is new_msg
    service.messageRepository.create.assert_called_once()


def test_sendMessage_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver", status=config.STATUS_CODES["enabled"])
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-stranger", "Hi")
    assert exc.value.statusCode == 403


def test_sendMessage_pending_chat_auto_activates(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["pending"])
    service.chatRepository.findById.return_value = chat
    service.messageRepository.create.return_value = _mock_message()

    service.sendMessage("chat-001", "uid-sender", "First message")
    service.chatRepository.updateStatus.assert_called_once()


def test_sendMessage_disabled_chat_raises_400(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["disabled"])
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-sender", "Hi")
    assert exc.value.statusCode == 400


def test_sendMessage_empty_content_raises_400(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["enabled"])
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-sender", "   ")
    assert exc.value.statusCode == 400


def test_sendMessage_over_the_limit_raises_400_before_anything_is_written(mock_db):
    """The socket path has no schema, so the service is the only cap it meets."""
    from domain.services.messageService import MAX_MESSAGE_LENGTH
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat(
        sender="uid-sender", status=config.STATUS_CODES["enabled"]
    )

    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-sender", "a" * (MAX_MESSAGE_LENGTH + 1))
    assert exc.value.statusCode == 400
    assert exc.value.errorCode == "MESSAGE_TOO_LONG"
    service.messageRepository.create.assert_not_called()


def test_sendMessage_at_the_limit_is_accepted(mock_db):
    from domain.services.messageService import MAX_MESSAGE_LENGTH
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat(
        sender="uid-sender", status=config.STATUS_CODES["enabled"]
    )

    service.sendMessage("chat-001", "uid-sender", "a" * MAX_MESSAGE_LENGTH)
    service.messageRepository.create.assert_called_once()


def test_sendMessage_non_text_content_raises_400(mock_db):
    service = _make_service(mock_db)
    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-sender", {"not": "text"})
    assert exc.value.statusCode == 400


def test_sendMessage_html_content_is_sanitized(mock_db):
    """Script tags are stripped; inner text preserved → MessageModel called with clean content."""
    from unittest.mock import patch as _patch

    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["enabled"])
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
    chat = _mock_chat(sender="uid-sender", status=config.STATUS_CODES["enabled"])
    service.chatRepository.findById.return_value = chat

    # bleach strips tags + content for empty-body tags: "<b></b>" → ""
    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-sender", "<b></b>")
    assert exc.value.statusCode == 400


# ── markAsRead ────────────────────────────────────────────────────────────────

def test_markAsRead_unread_message_marks_it(mock_db):
    service = _make_service(mock_db)
    msg = _mock_message(status=config.STATUS_CODES["unread"])
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver")
    service.messageRepository.findById.return_value = msg
    service.chatRepository.findById.return_value = chat
    read_msg = _mock_message(status=config.STATUS_CODES["read"])
    service.messageRepository.markAsRead.return_value = read_msg

    result = service.markAsRead("msg-001", "uid-receiver")
    assert result is read_msg
    service.messageRepository.markAsRead.assert_called_once_with("msg-001")


def test_markAsRead_already_read_is_idempotent(mock_db):
    service = _make_service(mock_db)
    msg = _mock_message(status=config.STATUS_CODES["read"])
    service.messageRepository.findById.return_value = msg

    result = service.markAsRead("msg-001", "uid-receiver")
    assert result is msg
    # Should not call markAsRead again
    service.messageRepository.markAsRead.assert_not_called()


def test_markAsRead_own_message_is_a_no_op(mock_db):
    """A sender cannot read their own message into a read receipt."""
    service = _make_service(mock_db)
    msg = _mock_message(sender="uid-sender", status=config.STATUS_CODES["unread"])
    service.messageRepository.findById.return_value = msg

    result = service.markAsRead("msg-001", "uid-sender")
    assert result is msg
    service.messageRepository.markAsRead.assert_not_called()


def test_markAsRead_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    msg = _mock_message(status=config.STATUS_CODES["unread"])
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
    service.messageRepository.markAllAsRead.assert_called_once_with("chat-001", "uid-receiver")


def test_markAllAsRead_non_participant_raises_403(mock_db):
    service = _make_service(mock_db)
    chat = _mock_chat(sender="uid-sender", reciver="uid-receiver")
    service.chatRepository.findById.return_value = chat

    with pytest.raises(NoHarmException) as exc:
        service.markAllAsRead("chat-001", "uid-stranger")
    assert exc.value.statusCode == 403


# ── official accounts ─────────────────────────────────────────────────────────

@pytest.fixture
def official():
    original = list(config.OFFICIAL_USER_IDS)
    config.OFFICIAL_USER_IDS = original + ["uid-official"]
    yield "uid-official"
    config.OFFICIAL_USER_IDS = original


def test_sendMessage_user_cannot_reply_to_official_chat(mock_db, official):
    service = _make_service(mock_db)
    service.chatRepository.findById.return_value = _mock_chat(sender=official, reciver="uid-receiver")

    with pytest.raises(NoHarmException) as exc:
        service.sendMessage("chat-001", "uid-receiver", "hi")

    assert exc.value.errorCode == "OFFICIAL_CHAT_READONLY"
    service.messageRepository.create.assert_not_called()


def test_broadcast_refuses_a_non_official_sender(mock_db, official):
    service = _make_service(mock_db)

    with pytest.raises(NoHarmException) as exc:
        service.broadcast("uid-sender", "hello")

    assert exc.value.statusCode == 404


def test_broadcast_reaches_every_active_user_but_officials(mock_db, official, monkeypatch):
    from domain.services import messageService as module

    users = [MagicMock(id="uid-a"), MagicMock(id="uid-b"), MagicMock(id=official)]
    monkeypatch.setattr(module, "UserRepository", lambda db: MagicMock(findAll=lambda: users))
    chatService = MagicMock()
    chatService.getOrCreateOfficial.side_effect = lambda o, r: _mock_chat(sender=o, reciver=r)
    monkeypatch.setattr(module, "ChatService", lambda db: chatService)
    monkeypatch.setattr(module.fcmService, "sendPushToUser", MagicMock())
    monkeypatch.setattr(module.emitter, "notifyNewMessage", MagicMock())

    service = _make_service(mock_db)
    sent = service.broadcast(official, "hello everyone")

    assert sent == 2
    recipients = [c.args[1] for c in chatService.getOrCreateOfficial.call_args_list]
    assert recipients == ["uid-a", "uid-b"]
