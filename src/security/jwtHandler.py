import secrets
import os

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from security.tokenBlacklist import TokenBlacklist
from core.config import config

class JwtHandler:
    """
    JWT token generation and validation.

    Issues two token types:
        - access:  short-lived (15 min), sent on every request
        - refresh: long-lived (7 days), used to issue new access tokens

    Each token carries a unique JTI that allows individual revocation
    via blacklist without invalidating all tokens for the user.

    Usage:
        handler = JwtHandler()

        accessToken  = handler.createAccessToken(userId)
        refreshToken = handler.createRefreshToken(userId)

        payload = handler.verifyToken(accessToken, "access")
        payload = handler.verifyToken(refreshToken, "refresh")

        handler.revokeToken(payload["jti"], payload["exp"])
    """

    _ACCESS_TYPE  = "access"
    _REFRESH_TYPE = "refresh"
    _ALGORITHM    = config.JWT_ALGORITHM

    _ACCESS_EXPIRE_MINUTES  = config.ACCESS_TOKEN_EXPIRE_MINUTES
    _REFRESH_EXPIRE_DAYS    = config.REFRESH_TOKEN_EXPIRE_DAYS

    _REQUIRED_CLAIMS = ["sub", "type", "exp", "iat", "jti"]


    def __init__(self, blacklist: TokenBlacklist):
        self._blacklist    = blacklist
        self._accessKey    = config.JWT_SECRET_KEY
        self._refreshKey   = config.JWT_REFRESH_SECRET_KEY


    # ── Generation ────────────────────────────────────────────────────────────

    def createAccessToken(self, userId: str) -> str:
        """
        Issues a short-lived access token (15 minutes).

        Args:
            userId: ID of the token owner

        Returns:
            Signed JWT as a string
        """
        expiresAt = datetime.now(timezone.utc) + timedelta(minutes=self._ACCESS_EXPIRE_MINUTES)

        return self._buildToken(
            userId    = userId,
            tokenType = self._ACCESS_TYPE,
            expiresAt = expiresAt,
            secret    = self._accessKey
        )


    def createRefreshToken(self, userId: str) -> str:
        """
        Issues a long-lived refresh token (7 days).

        Args:
            userId: ID of the token owner

        Returns:
            Signed JWT as a string
        """
        expiresAt = datetime.now(timezone.utc) + timedelta(days=self._REFRESH_EXPIRE_DAYS)

        return self._buildToken(
            userId    = userId,
            tokenType = self._REFRESH_TYPE,
            expiresAt = expiresAt,
            secret    = self._refreshKey
        )


    # ── Validation ────────────────────────────────────────────────────────────

    def verifyToken(self, token: str, tokenType: str) -> Optional[dict]:
        """
        Validates a JWT and returns the payload if valid.

        Checks performed in order:
            1. Signature and expiry (PyJWT)
            2. Required claims are present
            3. Token type matches the expected type
            4. Token is not on the blacklist

        Args:
            token:     JWT string
            tokenType: expected type — "access" or "refresh"

        Returns:
            Token payload if valid, None otherwise
        """
        secret = self._secretForType(tokenType)

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms = [self._ALGORITHM],
                options    = {
                    "verify_exp": True,
                    "verify_iat": True,
                    "require":    self._REQUIRED_CLAIMS
                }
            )
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

        if not self._hasValidType(payload, tokenType):
            return None

        if self._blacklist.isBlacklisted(payload["jti"]):
            return None

        return payload


    # ── Revocation ────────────────────────────────────────────────────────────

    def revokeToken(self, jti: str, exp: int) -> None:
        """
        Revokes a token by adding its JTI to the blacklist.

        Must be called on logout (access + refresh)
        and on refresh token rotation (old refresh token).

        Args:
            jti: 'jti' claim from the token payload
            exp: 'exp' claim from the token payload (Unix timestamp)
        """
        expiresAt = datetime.fromtimestamp(exp, tz=timezone.utc).replace(tzinfo=None)
        self._blacklist.add(jti, expiresAt)


    # ── Internal ──────────────────────────────────────────────────────────────

    def _buildToken(
        self,
        userId:    str,
        tokenType: str,
        expiresAt: datetime,
        secret:    str
    ) -> str:
        payload = {
            "sub":  userId,
            "type": tokenType,
            "exp":  expiresAt,
            "iat":  datetime.now(timezone.utc),
            "jti":  secrets.token_urlsafe(16)
        }

        return jwt.encode(payload, secret, algorithm=self._ALGORITHM)


    def _secretForType(self, tokenType: str) -> str:
        if tokenType == self._ACCESS_TYPE:
            return self._accessKey

        if tokenType == self._REFRESH_TYPE:
            return self._refreshKey

        raise ValueError(f"Invalid token type: {tokenType}")


    def _hasValidType(self, payload: dict, expectedType: str) -> bool:
        return payload.get("type") == expectedType


    def _loadSecret(self, envKey: str) -> str:
        secret = os.getenv(envKey)

        if not secret:
            raise EnvironmentError(
                f"Required environment variable not found: {envKey}"
            )

        return secret