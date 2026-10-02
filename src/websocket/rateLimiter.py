import time
from functools import wraps

import redis.asyncio as aioredis

from core.config import config

_redis: aioredis.Redis = aioredis.from_url(config.REDIS_URL, decode_responses=True)


class WsConnectionLimiter:
    """At most `maxPerUser` live sockets per account — the newest win.

    A sorted set per user in Redis, `sid → connect time`. A new connection is
    always accepted; when it takes the account past the cap, the **oldest**
    sockets are returned to be disconnected.

    It used to be a counter that refused the newest connection instead. Two
    things were wrong with that: a phone left open in a drawer locked out the
    laptop the person was actually using, and a counter only stays right if
    every disconnect is seen — a crashed worker left it high, and the account
    was refused for up to a day. A set of sids heals itself: a stale entry is
    simply the oldest one, and the next connection evicts it.
    """

    _PREFIX = "ws:conns:"
    _TTL_SECONDS = 86400

    # Atomic across instances: add this socket, then cut the set back to the
    # newest `max`, returning whatever was cut.
    _ADMIT = """
    redis.call('ZADD', KEYS[1], ARGV[1], ARGV[2])
    redis.call('EXPIRE', KEYS[1], ARGV[4])
    local excess = redis.call('ZCARD', KEYS[1]) - tonumber(ARGV[3])
    if excess <= 0 then return {} end
    local oldest = redis.call('ZRANGE', KEYS[1], 0, excess - 1)
    redis.call('ZREM', KEYS[1], unpack(oldest))
    return oldest
    """

    def __init__(self, maxPerUser: int = 3):
        self.maxPerUser = maxPerUser

    async def admit(self, userId: str, sid: str) -> list[str]:
        """Record `sid` for `userId`; return the sids to disconnect (oldest first)."""
        evicted = await _redis.eval(
            self._ADMIT, 1, self._PREFIX + userId,
            str(time.time()), sid, str(self.maxPerUser), str(self._TTL_SECONDS),
        )
        return [e for e in (evicted or []) if e != sid]

    async def onDisconnect(self, userId: str, sid: str) -> None:
        await _redis.zrem(self._PREFIX + userId, sid)


def wsLimit(maxCalls: int, windowSeconds: int):
    """Fixed-window rate limit decorator for Socket.IO event handlers.

    Keyed by userId + handler name. Emits 'ws_error' and short-circuits when exceeded.

    Usage:
        @sio.on("send_message")
        @wsLimit(maxCalls=30, windowSeconds=60)
        async def sendMessage(sid, data): ...
    """
    def decorator(handler):
        @wraps(handler)
        async def wrapper(sid, *args, **kwargs):
            from websocket.socketManager import sio  # lazy — avoids circular import
            session = await sio.get_session(sid)
            userId = session.get("userId", sid)
            key = f"ws:rate:{userId}:{handler.__name__}"
            count = await _redis.incr(key)
            if count == 1:
                await _redis.expire(key, windowSeconds)
            if count > maxCalls:
                await sio.emit(
                    "ws_error",
                    {"code": "RATE_LIMITED", "message": "Too many requests, slow down."},
                    to=sid,
                )
                return
            return await handler(sid, *args, **kwargs)
        return wrapper
    return decorator
