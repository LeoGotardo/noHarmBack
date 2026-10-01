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
    """Capture emits without a server. `emit` imports socketManager lazily.

    `_hasLoop` is forced True because this fixture stands for the **API
    process** — the one with an ASGI server and sockets attached. Without it
    the test process looks like a cron job, and `emit` correctly takes the
    write-only Redis path instead of the one these tests are about.
    """
    import sys
    fake = MagicMock()
    fake.sio = MagicMock()
    with patch.dict(sys.modules, {"websocket.socketManager": fake}), \
         patch.object(emitter, "_hasLoop", return_value=True), \
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


def test_notifyMessagesRead_carries_the_reader(sio):
    """Both participants get the event; without the reader's id the reader's own
    client marked its outgoing messages read as well."""
    emitter.notifyMessagesRead("chat-9", ["uid-a", "uid-b"], "uid-b")

    assert sio.sio.emit.call_args_list[0].args[1] == {
        "chatId": "chat-9",
        "readerId": "uid-b",
    }


# ── out-of-process emits ──────────────────────────────────────────────────────
#
# The cron jobs run as their own process: no ASGI server, no sockets, nothing
# for `_schedule` to schedule. Their alerts used to be dropped with a log line
# and no other symptom — an SSH login that notified nobody.

def test_without_a_loop_the_emit_goes_out_over_redis():
    with patch.object(emitter, "_hasLoop", return_value=False), \
         patch.object(emitter, "_publishOutOfProcess", return_value=True) as publish:
        emitter.emit("admin_alert", {"x": 1}, room="user_admin")

    publish.assert_called_once()
    assert publish.call_args.args[0] == "admin_alert"
    assert publish.call_args.args[2] == "user_admin"


def test_a_failed_publish_falls_back_to_scheduling(sio):
    """Not silently dropped: if the channel cannot be reached the old path still
    gets its chance, and logs when it cannot either."""
    with patch.object(emitter, "_hasLoop", return_value=False), \
         patch.object(emitter, "_publishOutOfProcess", return_value=False):
        emitter.emit("admin_alert", {"x": 1}, room="user_admin")

    assert sio.sio.emit.called


def test_notifyAdmins_reaches_every_admin(sio):
    with patch.object(emitter, "_hasLoop", return_value=True), \
         patch("core.roles.allAdminIds", return_value={"adm-1", "adm-2"}):
        emitter.notifyAdmins("host_access", "SSH login", "ubuntu from 1.2.3.4")

    assert sorted(_rooms(sio)) == ["user_adm-1", "user_adm-2"]
    payload = sio.sio.emit.call_args_list[0].args[1]
    assert payload["kind"] == "host_access"
    assert payload["title"] == "SSH login"


def test_notifyAdmins_with_no_admins_emits_nothing(sio):
    with patch.object(emitter, "_hasLoop", return_value=True), \
         patch("core.roles.allAdminIds", return_value=set()):
        emitter.notifyAdmins("error", "New error", "boom")

    assert not sio.sio.emit.called
