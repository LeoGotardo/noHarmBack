from datetime import datetime, timezone
from security.persistentHashTable import PersistentHashTable
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
        return self._storage.exists(hashedJti)


    def cleanup(self) -> None:
        """
        Removes all expired tokens from memory and from the backing file.
        Called automatically on startup and can be scheduled periodically
        to keep the file compact.
        """
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        self._storage.cleanup(
            isExpired=lambda exp: datetime.fromisoformat(exp) < now
        )


    # ── Internal ──────────────────────────────────────────────────────────────

    def _hash(self, jti: str) -> str:
        return Encryption.hash(jti)
