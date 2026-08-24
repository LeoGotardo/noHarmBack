"""Unit tests for the Redis-backed presence registry.

Presence was a module-level dict in socketManager, so it only ever described
one process. These run against fakeredis so the SET semantics that make a
multi-device user work are exercised for real, not asserted against a mock.
"""

import pytest
from unittest.mock import patch


@pytest.fixture
def redis():
    import fakeredis.aioredis
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def presence(redis):
    from websocket import presence as module
    with patch.object(module, "_redis", redis):
        yield module


# ── single connection ─────────────────────────────────────────────────────────

async def test_user_is_offline_before_connecting(presence):
    assert await presence.isOnline("uid-1") is False


async def test_user_is_online_after_add(presence):
    await presence.add("uid-1", "sid-a")
    assert await presence.isOnline("uid-1") is True


async def test_user_is_offline_after_remove(presence):
    await presence.add("uid-1", "sid-a")
    await presence.remove("uid-1", "sid-a")
    assert await presence.isOnline("uid-1") is False


async def test_presence_is_per_user(presence):
    await presence.add("uid-1", "sid-a")
    assert await presence.isOnline("uid-2") is False


# ── several devices ───────────────────────────────────────────────────────────

async def test_user_stays_online_until_the_last_device_drops(presence):
    """WsConnectionLimiter allows 3 connections per user; closing one tab must
    not mark the person offline on their phone."""
    await presence.add("uid-1", "sid-a")
    await presence.add("uid-1", "sid-b")

    await presence.remove("uid-1", "sid-a")
    assert await presence.isOnline("uid-1") is True

    await presence.remove("uid-1", "sid-b")
    assert await presence.isOnline("uid-1") is False


async def test_adding_the_same_sid_twice_is_idempotent(presence):
    await presence.add("uid-1", "sid-a")
    await presence.add("uid-1", "sid-a")
    await presence.remove("uid-1", "sid-a")
    assert await presence.isOnline("uid-1") is False


async def test_removing_an_unknown_sid_does_not_drop_the_user(presence):
    await presence.add("uid-1", "sid-a")
    await presence.remove("uid-1", "sid-ghost")
    assert await presence.isOnline("uid-1") is True


# ── self-heal ─────────────────────────────────────────────────────────────────

async def test_entries_carry_a_ttl(presence, redis):
    """An instance killed without running `disconnect` leaves its sids behind.
    Without the TTL that user would read as online forever."""
    await presence.add("uid-1", "sid-a")
    assert await redis.ttl("ws:presence:uid-1") > 0


async def test_ttl_is_refreshed_by_a_new_connection(presence, redis):
    await presence.add("uid-1", "sid-a")
    await redis.expire("ws:presence:uid-1", 5)
    await presence.add("uid-1", "sid-b")
    assert await redis.ttl("ws:presence:uid-1") > 5


# ── batch lookup ──────────────────────────────────────────────────────────────

async def test_onlineAmong_returns_only_connected_users(presence):
    await presence.add("uid-1", "sid-a")
    await presence.add("uid-3", "sid-c")

    assert await presence.onlineAmong(["uid-1", "uid-2", "uid-3"]) == {"uid-1", "uid-3"}


async def test_onlineAmong_with_no_ids_makes_no_call(presence):
    assert await presence.onlineAmong([]) == set()


async def test_onlineAmong_skips_empty_ids(presence):
    await presence.add("uid-1", "sid-a")
    assert await presence.onlineAmong(["uid-1", "", None]) == {"uid-1"}


# ── store unreachable ─────────────────────────────────────────────────────────
#
# Presence only drives an indicator. Message delivery does not consult it, so a
# wrong "online" is worse than a missing one — these fail closed.

class _DeadRedis:
    def __getattr__(self, _name):
        async def boom(*a, **k):
            raise ConnectionError("redis is down")
        return boom

    def pipeline(self):
        raise ConnectionError("redis is down")


@pytest.fixture
def dead_presence():
    from websocket import presence as module
    with patch.object(module, "_redis", _DeadRedis()):
        yield module


async def test_isOnline_reports_offline_when_the_store_is_down(dead_presence):
    assert await dead_presence.isOnline("uid-1") is False


async def test_onlineAmong_reports_nobody_when_the_store_is_down(dead_presence):
    assert await dead_presence.onlineAmong(["uid-1", "uid-2"]) == set()


async def test_add_does_not_raise_into_the_connect_handler(dead_presence):
    """A presence write failing must not refuse an otherwise valid connection."""
    await dead_presence.add("uid-1", "sid-a")


async def test_remove_does_not_raise_into_the_disconnect_handler(dead_presence):
    await dead_presence.remove("uid-1", "sid-a")
