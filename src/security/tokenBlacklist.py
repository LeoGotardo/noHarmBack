from datetime import datetime, timezone
from security.persistentHashTable import PersistentHashTable
from security.encryption import Encryption
from core.config import config


class TokenBlacklist:
    """
    Blacklist of revoked JWT tokens.

    Tokens added here are never removed manually — they are only evicted
    when they expire naturally, via cleanup.

    The JTI is stored as a SHA-256 hash to avoid writing the original
    value to disk in plaintext.

    Usage:
        blacklist = TokenBlacklist()
        blacklist.add(jti, expiresAt)
        blacklist.isBlacklisted(jti)  # True/False
        blacklist.cleanup()           # removes expired entries
    """

    _STORAGE_PATH = str(config.STORAGE_PATH + '/blacklist.jsonl')

    def __init__(self):
        self._storage = PersistentHashTable(self._STORAGE_PATH)
        self.cleanup()


    # ── Public interface ──────────────────────────────────────────────────────

    def add(self, jti: str, expiresAt: datetime) -> None:
        """
        Revokes a token by adding its JTI to the blacklist.

        Args:
            jti:       unique token ID ('jti' claim from the JWT)
            expiresAt: moment the token expires naturally
        """
        hashedJti = self._hash(jti)
        self._storage.set(hashedJti, expiresAt.isoformat())


    def isBlacklisted(self, jti: str) -> bool:
        """
        Checks whether a token has been revoked.

        Args:
            jti: unique token ID ('jti' claim from the JWT)

        Returns:
            True if the token is on the blacklist, False otherwise
        """
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
        """
        Returns the SHA-256 hash of the JTI.
        Plaintext JTIs are never stored on disk.
        """
        return Encryption.hash(jti)