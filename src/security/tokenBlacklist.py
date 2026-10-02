from datetime import datetime, timezone
from typing import Optional

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

    # ── every token of one account ────────────────────────────────────────────
    #
    # A JTI blacklist revokes the tokens you hold. "Log out everywhere" has to
    # revoke the ones you do not — a refresh token on a lost phone — so it is a
    # cutoff instead: every token of this account issued before the instant is
    # refused. One key per account, living exactly as long as the longest
    # token it could still have to refuse (a refresh token's lifetime).

    _CUTOFF_PREFIX = "revoked_before:"

    def revokeAllFor(self, userId: str, ttlSeconds: int) -> int:
        """Refuse every token of `userId` issued up to now. Returns the cutoff.

        The cutoff is the next whole second: `iat` has one-second resolution,
        so a token minted in this same second — before or after the call —
        cannot be told apart, and refusing it is the safe side.
        """
        cutoff = int(datetime.now(timezone.utc).timestamp()) + 1
        self._redis.setex(self._CUTOFF_PREFIX + Encryption.digest(str(userId)), ttlSeconds, str(cutoff))
        return cutoff

    def revokedBefore(self, userId: str) -> Optional[int]:
        """The cutoff set by `revokeAllFor`, or None."""
        raw = self._redis.get(self._CUTOFF_PREFIX + Encryption.digest(str(userId)))
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    def _hash(self, jti: str) -> str:
        # `digest`, not `hash`: a JTI is 128 bits of `secrets.token_urlsafe`, so
        # a keyed index protects nothing here — and it would tie every stored
        # revocation to BLIND_INDEX_KEY, so rotating that key would un-revoke
        # every token still within its lifetime.
        return Encryption.digest(jti)
