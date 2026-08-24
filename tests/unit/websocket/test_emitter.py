"""Unit tests for server → client emission.

`emitToChat` used to broadcast to `chat_{chatId}` and then top up the personal
room of any participant whose sid was not already in that room, deduplicating
via `sio.manager.get_participants`. That lookup is per-instance, so once the
backend runs on more than one instance a remote participant looked absent and
received the event twice. Delivery now goes to personal rooms only.

Nothing covered this module before; the double-delivery bug was invisible.
"""

import pytest
from unittest.mock import MagicMock, patch

from websocket import emitter


@pytest.fixture
def sio():
    """Capture emits without a server. `emit` imports socketManager lazily."""
    import sys
    fake = MagicMock()
    fake.sio = MagicMock()
    with patch.dict(sys.modules, {"websocket.socketManager": fake}), \
         patch.object(emitter, "_schedule") as schedule:
        fake.schedule = schedule
        yield fake


def _rooms(sio):
    """Rooms addressed, read off the emit calls that were scheduled."""
    return [call.kwargs["room"] for call in sio.sio.emit.call_args_list]


# ── emitToChat ────────────────────────────────────────────────────────────────

def test_every_participant_gets_the_event_in_their_personal_room(sio):
    emitter.emitToChat("chat-1", "new_message", {"x": 1}, ["uid-a", "uid-b"])

    assert sorted(_rooms(sio)) == ["user_uid-a", "user_uid-b"]


def test_the_chat_room_is_not_addressed(sio):
    """Addressing both the chat room and personal rooms is what delivered twice."""
    emitter.emitToChat("chat-1", "new_message", {"x": 1}, ["uid-a", "uid-b"])

    assert not any(room.startswith("chat_") for room in _rooms(sio))


def test_each_participant_is_addressed_once(sio):
    emitter.emitToChat("chat-1", "new_message", {"x": 1}, ["uid-a", "uid-b"])

    rooms = _rooms(sio)
    assert len(rooms) == len(set(rooms)) == 2


def test_a_repeated_participant_is_collapsed(sio):
    """A self-chat lists the same id as sender and receiver."""
    emitter.emitToChat("chat-1", "new_message", {"x": 1}, ["uid-a", "uid-a"])

    assert _rooms(sio) == ["user_uid-a"]


def test_participant_ids_are_stringified(sio):
    from uuid import UUID
    uid = UUID("11111111-2222-3333-4444-555555555555")
    emitter.emitToChat("chat-1", "new_message", {}, [uid])

    assert _rooms(sio) == [f"user_{uid}"]


def test_no_participants_emits_nothing(sio):
    emitter.emitToChat("chat-1", "new_message", {}, [])

    assert _rooms(sio) == []


def test_delivery_does_not_depend_on_presence(sio):
    """Presence lives in Redis and can be stale or unreachable. Emitting to a
    room nobody occupies is free, so an offline participant must not stop the
    event reaching the one who is connected."""
    with patch("websocket.presence.isOnline", side_effect=AssertionError("must not be consulted")):
        emitter.emitToChat("chat-1", "new_message", {}, ["uid-a", "uid-b"])

    assert len(_rooms(sio)) == 2


# ── public helpers ────────────────────────────────────────────────────────────

def test_notifyNewMessage_targets_both_participants(sio):
    message = MagicMock()
    message.chat = "chat-1"

    emitter.notifyNewMessage(message, ["uid-a", "uid-b"])

    assert sorted(_rooms(sio)) == ["user_uid-a", "user_uid-b"]
    assert sio.sio.emit.call_args_list[0].args[0] == "new_message"


def test_notifyMessagesRead_targets_both_participants(sio):
    emitter.notifyMessagesRead("chat-1", ["uid-a", "uid-b"])

    assert sorted(_rooms(sio)) == ["user_uid-a", "user_uid-b"]
    assert sio.sio.emit.call_args_list[0].args[0] == "messages_read"


def test_notifyMessagesRead_carries_the_chat_id(sio):
    emitter.notifyMessagesRead("chat-9", ["uid-a"])

    assert sio.sio.emit.call_args_list[0].args[1] == {"chatId": "chat-9"}
