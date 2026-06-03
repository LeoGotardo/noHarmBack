from datetime import datetime, timezone

import redis

from security.encryption import Encryption
from core.config import config


class TokenBlacklist:
    """
    Revoked JWT tokens stored in Redis with TTL-based auto-expiry.

    Usage:
        blacklist = TokenBlacklist()
        blacklist.add(jti, expiresAt)
        blacklist.isBlacklisted(jti)  # True/False
    """

    _PREFIX = "jti:"

    def __init__(self):
        self._redis: redis.Redis[str] = redis.from_url(config.REDIS_URL, decode_responses=True)  # type: ignore[assignment]

    def add(self, jti: str, expiresAt: datetime) -> None:
        hashedJti = self._hash(jti)
        if expiresAt.tzinfo is None:
            expiresAt = expiresAt.replace(tzinfo=timezone.utc)
        ttl = int((expiresAt - datetime.now(timezone.utc)).total_seconds())
        if ttl > 0:
            self._redis.setex(self._PREFIX + hashedJti, ttl, "1")

    def isBlacklisted(self, jti: str) -> bool:
        hashedJti = self._hash(jti)
        return self._redis.exists(self._PREFIX + hashedJti) == 1

    def _hash(self, jti: str) -> str:
        return Encryption.hash(jti)
