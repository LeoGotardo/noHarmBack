from datetime import datetime

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
        self._redis = redis.from_url(config.REDIS_URL, decode_responses=True)

    def add(self, jti: str, expiresAt: datetime) -> None:
        hashedJti = self._hash(jti)
        ttl = int((expiresAt - datetime.utcnow()).total_seconds())
        if ttl > 0:
            self._redis.setex(self._PREFIX + hashedJti, ttl, "1")

    def isBlacklisted(self, jti: str) -> bool:
        hashedJti = self._hash(jti)
        return self._redis.exists(self._PREFIX + hashedJti) == 1

    def _hash(self, jti: str) -> str:
        return Encryption.hash(jti)
