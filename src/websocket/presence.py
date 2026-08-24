"""Who is currently connected, shared across instances.

Presence used to be a module-level `dict[userId, sid]` living in socketManager.
That dict only ever described the process holding it. On serverless that is one
instance out of several: a user connected to instance B1 read as offline from
B2, and the REST invocation that persists a message has no sockets attached at
all.

State now lives in Redis, in the same style as `WsConnectionLimiter`. One SET of
sids per user, so someone signed in on three devices stays online until the last
one drops.

The TTL is a self-heal, not an expiry policy: an instance killed without running
its `disconnect` handler leaves its sids behind, and without a TTL that user
would read as online forever.

Redis being unreachable reports users as **offline**. Presence only drives an
indicator, and a wrong "online" is worse than a missing one — message delivery
does not depend on this module.
"""

import logging

import redis.asyncio as aioredis

from core.config import config

logger = logging.getLogger(__name__)

_PREFIX = "ws:presence:"
_TTL_SECONDS = 86400

_redis: aioredis.Redis = aioredis.from_url(config.REDIS_URL, decode_responses=True)  # type: ignore[assignment]


def _key(userId: str) -> str:
    return f"{_PREFIX}{userId}"


async def add(userId: str, sid: str) -> None:
    """Record that `sid` belongs to `userId` and is connected."""
    try:
        key = _key(userId)
        await _redis.sadd(key, sid)  # type: ignore[misc]
        await _redis.expire(key, _TTL_SECONDS)
    except Exception:
        logger.exception("could not record presence for %s", userId)


async def remove(userId: str, sid: str) -> None:
    """Drop one connection. The user stays online while other sids remain."""
    try:
        await _redis.srem(_key(userId), sid)  # type: ignore[misc]
    except Exception:
        logger.exception("could not clear presence for %s", userId)


async def isOnline(userId: str) -> bool:
    try:
        return bool(await _redis.exists(_key(userId)))
    except Exception:
        logger.exception("could not read presence for %s", userId)
        return False


async def onlineAmong(userIds: list[str]) -> set[str]:
    """Which of `userIds` are connected — one round trip, not one per user."""
    ids = [uid for uid in userIds if uid]
    if not ids:
        return set()
    try:
        pipe = _redis.pipeline()
        for userId in ids:
            pipe.exists(_key(userId))
        results = await pipe.execute()
        return {userId for userId, online in zip(ids, results) if online}
    except Exception:
        logger.exception("could not read presence for %d users", len(ids))
        return set()
