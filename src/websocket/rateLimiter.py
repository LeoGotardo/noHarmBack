from functools import wraps

import redis.asyncio as aioredis

from core.config import config

_redis: aioredis.Redis = aioredis.from_url(config.REDIS_URL, decode_responses=True)


class WsConnectionLimiter:
    """Redis-backed per-user WebSocket connection counter."""

    _PREFIX = "ws:conn:"

    def __init__(self, maxPerUser: int = 3):
        self.maxPerUser = maxPerUser

    async def tryConnect(self, userId: str) -> bool:
        key = self._PREFIX + userId
        count = await _redis.incr(key)
        await _redis.expire(key, 86400)
        if count > self.maxPerUser:
            await _redis.decr(key)
            return False
        return True

    async def onDisconnect(self, userId: str) -> None:
        key = self._PREFIX + userId
        current = await _redis.get(key)
        if current and int(current) > 0:
            await _redis.decr(key)


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
