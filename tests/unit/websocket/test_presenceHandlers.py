"""Unit tests for the presence Socket.IO handler.

`get_online_status` had no tests and answered for any id at all: an account
could watch anyone it could name — including someone who had blocked it — and
the reply was one emit per requested id, so an unbounded list was an
amplification lever.

`register()` takes the server as an argument, so a fake that records what the
handler does is enough — no event loop plumbing, no real Socket.IO.
"""

import pytest
from typing import Any, cast
from unittest.mock import MagicMock, patch

from core.config import config


_ACCEPTED = config.STATUS_CODES["accepted"]
_PENDING = config.STATUS_CODES["pending"]
_BLOCKED = config.STATUS_CODES["blocked"]


class FakeSio:
    def __init__(self, userId="uid-001"):
        self.handlers = {}
        self._session = {"userId": userId}
        self.emitted = []

    def on(self, event):
        def decorator(handler):
            self.handlers[event] = handler
            return handler
        return decorator

    async def get_session(self, sid):
        return self._session

    async def emit(self, event, data=None, **kwargs):
        self.emitted.append((event, data, kwargs))

    # assertions
    def statuses(self):
        return {d["userId"]: d["online"] for e, d, _ in self.emitted if e == "online_status"}

    def errors(self):
        return [d for e, d, _ in self.emitted if e == "error"]


def _friendship(sender, reciver, status=_ACCEPTED):
    f = MagicMock()
    f.sender = sender
    f.reciver = reciver
    f.status = status
    return f


@pytest.fixture
def sio():
    from websocket.handlers import presenceHandlers

    fake = FakeSio()
    service = MagicMock()
    service.return_value.getAll.return_value = []

    with patch.object(presenceHandlers, "database", MagicMock()), \
         patch.object(presenceHandlers, "RLSContext"), \
         patch.object(presenceHandlers, "FriendshipService", service), \
         patch.object(presenceHandlers, "_DbProxy", lambda s: MagicMock(session=s)):
        presenceHandlers.register(cast(Any, fake))
        fake.friendshipService = service
        yield fake


@pytest.fixture
def online():
    from websocket.handlers import presenceHandlers

    async def _onlineAmong(userIds):
        return {uid for uid in userIds if uid.endswith("-on")}

    with patch.object(presenceHandlers.presence, "onlineAmong", _onlineAmong):
        yield


def _friends(sio, *userIds, status=_ACCEPTED):
    sio.friendshipService.return_value.getAll.return_value = [
        _friendship("uid-001", uid, status) for uid in userIds
    ]


# ── authorisation ─────────────────────────────────────────────────────────────

async def test_answers_for_an_accepted_friend(sio, online):
    _friends(sio, "friend-on")

    await sio.handlers["get_online_status"]("sid-1", {"userIds": ["friend-on"]})

    assert sio.statuses() == {"friend-on": True}


async def test_says_nothing_about_a_stranger(sio, online):
    """Not `false` — an answer of any kind confirms the account exists, which is
    what made the handler an id-enumeration oracle."""
    _friends(sio, "friend-on")

    await sio.handlers["get_online_status"]("sid-1", {"userIds": ["stranger-on"]})

    assert sio.statuses() == {}


async def test_says_nothing_about_a_pending_request(sio, online):
    _friends(sio, "pending-on", status=_PENDING)

    await sio.handlers["get_online_status"]("sid-1", {"userIds": ["pending-on"]})

    assert sio.statuses() == {}


async def test_says_nothing_about_a_blocked_relationship(sio, online):
    """Someone who blocked you must not stay watchable."""
    _friends(sio, "blocker-on", status=_BLOCKED)

    await sio.handlers["get_online_status"]("sid-1", {"userIds": ["blocker-on"]})

    assert sio.statuses() == {}


async def test_finds_the_friend_on_either_side_of_the_row(sio, online):
    """Friendship rows are directional; the caller may be sender or receiver."""
    sio.friendshipService.return_value.getAll.return_value = [
        _friendship("friend-on", "uid-001")
    ]

    await sio.handlers["get_online_status"]("sid-1", {"userIds": ["friend-on"]})

    assert sio.statuses() == {"friend-on": True}


async def test_mixed_request_answers_only_the_friends(sio, online):
    _friends(sio, "friend-on", "other-off")

    await sio.handlers["get_online_status"](
        "sid-1", {"userIds": ["friend-on", "other-off", "stranger-on"]}
    )

    assert sio.statuses() == {"friend-on": True, "other-off": False}


async def test_scopes_the_friendship_read_to_the_socket_owner(sio, online):
    """The list read must be the caller's, not one named in the payload."""
    await sio.handlers["get_online_status"]("sid-1", {"userIds": ["x"], "userId": "victim"})

    sio.friendshipService.return_value.getAll.assert_called_once_with("uid-001")


# ── bounds ────────────────────────────────────────────────────────────────────

async def test_rejects_more_ids_than_the_ceiling(sio, online):
    """One frame in must not buy an unbounded number of frames out."""
    from websocket.handlers.presenceHandlers import _MAX_QUERY_IDS

    ids = [f"u{i}-on" for i in range(_MAX_QUERY_IDS + 1)]
    _friends(sio, *ids)

    await sio.handlers["get_online_status"]("sid-1", {"userIds": ids})

    assert sio.statuses() == {}
    assert sio.errors() == [
        {"code": "TOO_MANY_IDS", "message": f"At most {_MAX_QUERY_IDS} userIds per query."}
    ]


async def test_accepts_exactly_the_ceiling(sio, online):
    from websocket.handlers.presenceHandlers import _MAX_QUERY_IDS

    ids = [f"u{i}-on" for i in range(_MAX_QUERY_IDS)]
    _friends(sio, *ids)

    await sio.handlers["get_online_status"]("sid-1", {"userIds": ids})

    assert sio.errors() == []
    assert len(sio.statuses()) == _MAX_QUERY_IDS


async def test_a_repeated_id_is_answered_once(sio, online):
    _friends(sio, "friend-on")

    await sio.handlers["get_online_status"]("sid-1", {"userIds": ["friend-on"] * 50})

    assert len([e for e, _, _ in sio.emitted if e == "online_status"]) == 1


async def test_rejects_a_non_list_payload(sio, online):
    await sio.handlers["get_online_status"]("sid-1", {"userIds": "friend-on"})

    assert sio.errors() == [{"code": "INVALID_DATA", "message": "userIds must be a list"}]


async def test_an_empty_request_reads_nothing(sio, online):
    await sio.handlers["get_online_status"]("sid-1", {"userIds": []})

    assert sio.statuses() == {}
    sio.friendshipService.return_value.getAll.assert_not_called()
