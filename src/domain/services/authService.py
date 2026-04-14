from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.models.userModel import UserModel
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from schemas.authSchemas import AuthRegisterRequest, AuthLoginRequest
from security.jwtHandler import JwtHandler
from security.tokenBlacklist import TokenBlacklist
from security.rateLimiter import LoginRateLimiter
from security.sanitizer import Sanitizer
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database

import re
import uuid
from datetime import datetime

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,50}$')


_blacklist = TokenBlacklist()
_jwtHandler = JwtHandler(_blacklist)
_loginLimiter = LoginRateLimiter()


class AuthService:
    def __init__(self, db: Database):
        self.db = db
        self.userRepository = UserRepository(db)
        self.auditRepository = AuditLogsRepository(db)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _logAudit(self, actionType: int, catalystId: str, description: str) -> None:
        """Create an audit log entry. Failures are silently ignored to not block main flow."""
        try:
            entry = AuditLogsModel(
                type=actionType,
                catalyst_id=catalystId,
                catalyst=None,
                description=description
            )
            self.auditRepository.create(entry)
        except Exception:
            pass

    # ── register ──────────────────────────────────────────────────────────────

    def register(self, request: AuthRegisterRequest) -> dict:
        """Create a new user account using Firebase identity data.

        Rules (§1.1):
        - username must match ^[a-zA-Z0-9_-]+$ and be 3–50 chars
        - username and email must be globally unique → 409 (generic message)
        - status = pending until email verification (enabled if Firebase already verified)
        - password is never stored here (Firebase handles auth)

        Returns:
            dict with accessToken, refreshToken, tokenType
        """
        username: str = request.username
        email: str = request.email
        uid: str = request.uid

        # Rule 1.1 — username format (3–50 chars, ^[a-zA-Z0-9_-]+$)
        username = Sanitizer.cleanHtml(username)
        if not _USERNAME_RE.match(username):
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_USERNAME",
                message="Username must be 3–50 characters and contain only letters, numbers, _ or -."
            )

        # Rule 1.1 — uniqueness (generic 409 to prevent enumeration)
        try:
            self.userRepository.findByEmail(email)
            raise NoHarmException(statusCode=409, errorCode="CONFLICT", message="Registration failed. Please check your details.")
        except NoHarmException as e:
            if e.statusCode == 409:
                raise e
            # 404 → email is available, continue

        try:
            self.userRepository.findByUsername(username)
            raise NoHarmException(statusCode=409, errorCode="CONFLICT", message="Registration failed. Please check your details.")
        except NoHarmException as e:
            if e.statusCode == 409:
                raise e
            # 404 → username is available, continue

        photoBytes: bytes = request.photoURL.encode("utf-8") if request.photoURL else b""
        status = config.STATUS_CODES["enabled"] if request.emailVerified else config.STATUS_CODES["pending"]

        newUser = UserModel(
            id=uid,
            username=username,
            email=email,
            profile_picture=photoBytes,
            status=status
        )
        self.userRepository.create(newUser)

        accessToken = _jwtHandler.createAccessToken(str(uid))
        refreshToken = _jwtHandler.createRefreshToken(str(uid))

        return {
            "accessToken": accessToken,
            "refreshToken": refreshToken,
            "tokenType": "Bearer"
        }

    # ── login ─────────────────────────────────────────────────────────────────

    def login(self, request: AuthLoginRequest) -> dict:
        """Authenticate via Firebase identity and issue token pair.

        Rules (§1.2, §1.4, §8.1):
        - Rate-limited per UID (5 attempts / 15 min → 30 min lockout)
        - banned / blocked / deleted accounts → 403
        - On failure: generic 'Invalid credentials' response
        - On success: audit log type=1; on failure: type=2

        Returns:
            dict with accessToken, refreshToken, tokenType
        """
        uid: str = request.uid

        # Rate limiting (§9.6)
        allowed, reason = _loginLimiter.check(uid)
        if not allowed:
            raise NoHarmException(statusCode=429, errorCode="TOO_MANY_REQUESTS", message=reason)

        genericError = NoHarmException(
            statusCode=401,
            errorCode="INVALID_CREDENTIALS",
            message="Invalid credentials."
        )

        try:
            user = self.userRepository.findById(uid)
        except NoHarmException:
            self._logAudit(2, uid, "Failed login — user not found")
            raise genericError

        # Rule 1.4 — reject banned / blocked / deleted
        blocked_statuses = {
            config.STATUS_CODES.get("banned"),
            config.STATUS_CODES.get("blocked"),
            config.STATUS_CODES.get("deleted"),
        }
        if user.status in blocked_statuses:
            self._logAudit(2, str(user.id), f"Failed login — account status {user.status}")
            match user.status:
                case s if s == config.STATUS_CODES.get("banned"):
                    raise NoHarmException(statusCode=403, errorCode="ACCOUNT_BANNED", message="Account is banned.")
                case s if s == config.STATUS_CODES.get("blocked"):
                    raise NoHarmException(statusCode=403, errorCode="ACCOUNT_BLOCKED", message="Account is blocked.")
                case _:
                    raise NoHarmException(statusCode=403, errorCode="ACCOUNT_DELETED", message="Account not found.")

        _loginLimiter.onSuccess(uid)
        self._logAudit(1, str(user.id), "Successful login")

        accessToken = _jwtHandler.createAccessToken(str(user.id))
        refreshToken = _jwtHandler.createRefreshToken(str(user.id))

        return {
            "accessToken": accessToken,
            "refreshToken": refreshToken,
            "tokenType": "Bearer"
        }

    # ── refresh ───────────────────────────────────────────────────────────────

    def refresh(self, refreshToken: str) -> dict:
        """Rotate refresh token and issue new token pair (§2.2).

        Returns:
            dict with new accessToken, refreshToken, tokenType
        """
        payload = _jwtHandler.verifyToken(refreshToken, "refresh")
        if not payload:
            raise NoHarmException(
                statusCode=401,
                errorCode="INVALID_TOKEN",
                message="Invalid or expired refresh token."
            )

        # Rotate: revoke old refresh token (§2.2)
        _jwtHandler.revokeToken(payload["jti"], payload["exp"])

        userId = payload["sub"]
        return {
            "accessToken": _jwtHandler.createAccessToken(userId),
            "refreshToken": _jwtHandler.createRefreshToken(userId),
            "tokenType": "Bearer"
        }

    # ── logout ────────────────────────────────────────────────────────────────

    def logout(self, accessToken: str, refreshToken: str) -> None:
        """Revoke both tokens and write audit log type=6 (§2.3, §8.1)."""
        userId = None

        for token, tokenType in [(accessToken, "access"), (refreshToken, "refresh")]:
            payload = _jwtHandler.verifyToken(token, tokenType)
            if payload:
                if tokenType == "access":
                    userId = payload.get("sub")
                _jwtHandler.revokeToken(payload["jti"], payload["exp"])

        if userId:
            self._logAudit(6, userId, "Token revocation — logout")
