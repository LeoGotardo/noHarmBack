"""Unit tests for the chat Socket.IO handlers.

chatHandlers.py sat at 29%: the REST path to a chat is guarded by
getCurrentUser plus RLS, but the socket path re-implements that guard by hand
(read userId off the session, set the RLS context, let ChatService assert
participation) and none of it was exercised. An authorisation hole here is not
visible from any route test.

`register()` takes the server as an argument, so a fake server that records
what handlers do is enough — no event loop plumbing, no real Socket.IO.
"""

import sys
import pytest
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

from exceptions.baseExceptions import NoHarmException


class FakeSio:
    """Captures registrations and calls instead of talking to a real server."""

    def __init__(self, session=None):
        self.handlers = {}
        self._session = session if session is not None else {"userId": "uid-001"}
        self.emitted = []
        self.rooms_entered = []
        self.rooms_left = []
        # Filled in by the `sio` fixture so each test can reach the patched
        # collaborators through the same object it drives the handlers with.
        self.rls = None
        self.chatService = None
        self.messageService = None

    # registration
    def on(self, event):
        def decorator(handler):
            self.handlers[event] = handler
            return handler
        return decorator

    # runtime
    async def get_session(self, sid):
        return self._session

    async def emit(self, event, data=None, **kwargs):
        self.emitted.append((event, data, kwargs))

    async def enter_room(self, sid, room):
        self.rooms_entered.append(room)

    async def leave_room(self, sid, room):
        self.rooms_left.append(room)

    def rooms(self, sid, namespace=None):
        """Rooms this sid has joined — synchronous, like the real AsyncServer's.

        `typing` reads this instead of re-asserting participation per keystroke,
        so the double has to model membership rather than just record the calls.
        """
        return [room for room in self.rooms_entered if room not in self.rooms_left]

    # assertions
    def errors(self):
        return [data for event, data, _ in self.emitted if event == "chat_error"]


@pytest.fixture
def session():
    """The SQLAlchemy session the handlers open and must always close."""
    return MagicMock()


@pytest.fixture
def sio(session):
    from websocket.handlers import chatHandlers

    db = MagicMock()
    db.session = session

    fake = FakeSio()
    with patch.object(chatHandlers, "database", db), \
         patch.object(chatHandlers, "RLSContext") as rls, \
         patch.object(chatHandlers, "ChatService") as chatService, \
         patch.object(chatHandlers, "MessageService") as messageService, \
         patch.object(chatHandlers, "_DbProxy", lambda s: MagicMock(session=s)):
        chatHandlers.register(cast(Any, fake))
        fake.rls = rls
        fake.chatService = chatService
        fake.messageService = messageService
        yield fake


@pytest.fixture(autouse=True)
def bypass_ws_rate_limit():
    """send_message and typing are wrapped in @wsLimit, which reaches for Redis
    and lazily imports websocket.socketManager. Neither is under test here."""
    redis = AsyncMock()
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)

    fakeManager = MagicMock()
    fakeManager.sio = AsyncMock()
    fakeManager.sio.get_session = AsyncMock(return_value={"userId": "uid-001"})

    with patch("websocket.rateLimiter._redis", redis), \
         patch.dict(sys.modules, {"websocket.socketManager": fakeManager}):
        yield


# ── join_chat ─────────────────────────────────────────────────────────────────

async def test_join_chat_enters_the_room_for_a_participant(sio):
    await sio.handlers["join_chat"]("sid-1", {"chatId": "chat-9"})

    assert sio.rooms_entered == ["chat_chat-9"]
    assert sio.errors() == []


async def test_join_chat_checks_participation_before_joining(sio):
    """ChatService.get(chatId, userId) is what asserts membership."""
    await sio.handlers["join_chat"]("sid-1", {"chatId": "chat-9"})

    sio.chatService.return_value.get.assert_called_once_with("chat-9", "uid-001")


async def test_join_chat_refuses_a_chat_the_user_is_not_in(sio):
    sio.chatService.return_value.get.side_effect = NoHarmException(
        statusCode=403, errorCode="ACCESS_DENIED", message="Not a participant."
    )

    await sio.handlers["join_chat"]("sid-1", {"chatId": "someone-elses-chat"})

    assert sio.rooms_entered == []
    assert sio.errors() == [{"code": "ACCESS_DENIED", "message": "Not a participant."}]


async def test_join_chat_sets_the_rls_context_to_the_socket_owner(sio, session):
    await sio.handlers["join_chat"]("sid-1", {"chatId": "chat-9"})

    assert sio.rls.setUserId.call_args[0][1] == "uid-001"


@pytest.mark.parametrize("payload", [None, {}, {"chatId": ""}, {"chatId": None}])
async def test_join_chat_rejects_a_missing_chat_id(sio, payload):
    await sio.handlers["join_chat"]("sid-1", payload)

    assert sio.rooms_entered == []
    assert sio.errors() == [{"code": "INVALID_DATA", "message": "chatId required"}]


async def test_join_chat_closes_the_session_on_success(sio, session):
    await sio.handlers["join_chat"]("sid-1", {"chatId": "chat-9"})
    session.close.assert_called_once()


async def test_join_chat_closes_the_session_when_refused(sio, session):
    """A leaked session per rejected join is a slow connection-pool drain."""
    sio.chatService.return_value.get.side_effect = NoHarmException(
        statusCode=403, errorCode="ACCESS_DENIED", message="nope"
    )
    await sio.handlers["join_chat"]("sid-1", {"chatId": "chat-9"})
    session.close.assert_called_once()


# ── leave_chat ────────────────────────────────────────────────────────────────

async def test_leave_chat_leaves_the_room(sio):
    await sio.handlers["leave_chat"]("sid-1", {"chatId": "chat-9"})
    assert sio.rooms_left == ["chat_chat-9"]


async def test_leave_chat_without_chat_id_is_a_no_op(sio):
    await sio.handlers["leave_chat"]("sid-1", {})
    assert sio.rooms_left == []


# ── send_message ──────────────────────────────────────────────────────────────

async def test_send_message_delegates_to_the_service(sio):
    """The socket path must go through the same service the REST path uses, so
    broadcast and push behaviour cannot drift between them."""
    await sio.handlers["send_message"]("sid-1", {"chatId": "chat-9", "content": "hi"})

    sio.messageService.return_value.sendMessage.assert_called_once_with(
        "chat-9", "uid-001", "hi"
    )


async def test_send_message_uses_the_session_user_not_the_payload(sio):
    """Sender identity comes from the authenticated socket session. If it were
    read off the payload, any client could post as anyone."""
    await sio.handlers["send_message"](
        "sid-1", {"chatId": "chat-9", "content": "hi", "userId": "victim"}
    )

    assert sio.messageService.return_value.sendMessage.call_args[0][1] == "uid-001"


@pytest.mark.parametrize("payload", [
    None, {}, {"chatId": "c"}, {"content": "hi"}, {"chatId": "c", "content": ""},
])
async def test_send_message_rejects_incomplete_payloads(sio, payload):
    await sio.handlers["send_message"]("sid-1", payload)

    sio.messageService.return_value.sendMessage.assert_not_called()
    assert sio.errors() == [{"code": "INVALID_DATA", "message": "chatId and content required"}]


async def test_send_message_reports_a_service_rejection_to_the_sender(sio):
    sio.messageService.return_value.sendMessage.side_effect = NoHarmException(
        statusCode=403, errorCode="ACCESS_DENIED", message="Not a participant."
    )

    await sio.handlers["send_message"]("sid-1", {"chatId": "chat-9", "content": "hi"})

    assert sio.errors() == [{"code": "ACCESS_DENIED", "message": "Not a participant."}]


async def test_send_message_closes_the_session_on_failure(sio, session):
    sio.messageService.return_value.sendMessage.side_effect = NoHarmException(
        statusCode=403, errorCode="ACCESS_DENIED", message="nope"
    )
    await sio.handlers["send_message"]("sid-1", {"chatId": "chat-9", "content": "hi"})
    session.close.assert_called_once()


# ── mark_read ─────────────────────────────────────────────────────────────────

async def test_mark_read_delegates_to_the_service(sio):
    await sio.handlers["mark_read"]("sid-1", {"chatId": "chat-9"})

    sio.messageService.return_value.markAllAsRead.assert_called_once_with(
        "chat-9", "uid-001"
    )


async def test_mark_read_rejects_a_missing_chat_id(sio):
    await sio.handlers["mark_read"]("sid-1", {})

    sio.messageService.return_value.markAllAsRead.assert_not_called()
    assert sio.errors() == [{"code": "INVALID_DATA", "message": "chatId required"}]


async def test_mark_read_closes_the_session(sio, session):
    await sio.handlers["mark_read"]("sid-1", {"chatId": "chat-9"})
    session.close.assert_called_once()


# ── typing ────────────────────────────────────────────────────────────────────

async def _joined(sio, chatId="chat-9"):
    """Put the socket in the chat room, as `join_chat` would after its own check."""
    await sio.enter_room("sid-1", f"chat_{chatId}")



async def test_typing_broadcasts_to_the_chat_room(sio):
    await _joined(sio)
    await sio.handlers["typing"]("sid-1", {"chatId": "chat-9", "isTyping": True})

    event, data, kwargs = sio.emitted[-1]
    assert event == "typing_indicator"
    assert data == {"chatId": "chat-9", "userId": "uid-001", "isTyping": True}
    assert kwargs["room"] == "chat_chat-9"


async def test_typing_does_not_echo_back_to_the_sender(sio):
    await _joined(sio)
    await sio.handlers["typing"]("sid-1", {"chatId": "chat-9", "isTyping": True})

    assert sio.emitted[-1][2]["skip_sid"] == "sid-1"


async def test_typing_defaults_to_not_typing(sio):
    await _joined(sio)
    await sio.handlers["typing"]("sid-1", {"chatId": "chat-9"})

    assert sio.emitted[-1][1]["isTyping"] is False


async def test_typing_coerces_a_truthy_value_to_bool(sio):
    await _joined(sio)
    await sio.handlers["typing"]("sid-1", {"chatId": "chat-9", "isTyping": "yes"})

    assert sio.emitted[-1][1]["isTyping"] is True


async def test_typing_rejects_a_missing_chat_id(sio):
    await sio.handlers["typing"]("sid-1", {})

    assert sio.errors() == [{"code": "INVALID_DATA", "message": "chatId required"}]


async def test_typing_carries_the_session_user_not_the_payload(sio):
    await _joined(sio)
    await sio.handlers["typing"](
        "sid-1", {"chatId": "chat-9", "isTyping": True, "userId": "victim"}
    )

    assert sio.emitted[-1][1]["userId"] == "uid-001"


async def test_typing_refuses_a_chat_the_socket_has_not_joined(sio):
    """The hole this closes: emitting to a room never required being in it, so
    naming any chatId put a typing indicator into a stranger's conversation."""
    await sio.handlers["typing"]("sid-1", {"chatId": "someone-elses-chat", "isTyping": True})

    assert [event for event, _, _ in sio.emitted] == ["chat_error"]
    assert sio.errors() == [
        {"code": "NOT_IN_CHAT", "message": "Join the chat before sending typing updates."}
    ]


async def test_typing_stops_after_leaving_the_chat(sio):
    """`leave_chat` takes the socket out of the room, and the guard reads live
    membership — so it must start refusing again."""
    await _joined(sio)
    await sio.handlers["leave_chat"]("sid-1", {"chatId": "chat-9"})

    await sio.handlers["typing"]("sid-1", {"chatId": "chat-9", "isTyping": True})

    assert sio.errors() == [
        {"code": "NOT_IN_CHAT", "message": "Join the chat before sending typing updates."}
    ]
