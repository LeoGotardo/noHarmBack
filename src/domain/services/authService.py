from infrastructure.database.repositories.userRepository import UserRepository
from domain.entities.user import User
from security.jwtHandler import JwtHandler
from security.tokenBlacklist import TokenBlacklist
from security.rateLimiter import LoginRateLimiter
from security.encryption import Encryption
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database

import uuid
from datetime import datetime


_blacklist = TokenBlacklist()
_jwtHandler = JwtHandler(_blacklist)
_loginLimiter = LoginRateLimiter()
_encryption = Encryption()


class AuthService:
    def __init__(self, db: Database):
        self.db = db
        self.userRepository = UserRepository(db)


    def register(self, user: dict) -> dict:
        _uuid: uuid = user["uid"]
        _email: str = user["email"]
        _username: str = user["username"]
        _photo: bytes = user["photoURL"].encode("utf-8")
        
        newUser = User(
            id = str(_uuid),
            username = _username,
            email = _email,
            profile_picture = _photo,
            status = config.STATUS_CODES["active"] if user["emailVerified"] else config.STATUS_CODES["pending"]
            )
        
        return self.userRepository.create(newUser)



    def login(self, user: dict) -> dict:
        """Authenticate a user and issue token pair.

        Args:
            user: Firebase user object

        Returns:
            dict with accessToken, refreshToken, tokenType
        """
        
        _uuid: uuid = user["uid"]
        _email: str = user["email"]
        
        # rate limiting por username/email (security.md §1.2)
        allowed, reason = _loginLimiter.check(_uuid)
        if not allowed:
            raise NoHarmException(statusCode=429, errorCode="TOO_MANY_REQUESTS", message=reason)

        # mensagem genérica — não revela se email existe ou senha está errada (security.md §7.1)
        genericError = NoHarmException(
            statusCode=401,
            errorCode="INVALID_CREDENTIALS",
            message="Invalid credentials."
        )

        try:
            logged_user = self.userRepository.findById(_uuid)
        except NoHarmException:
            raise genericError

        match logged_user.status:
            case config.STATUS_CODES.get("banned"):
                raise NoHarmException(statusCode=403, errorCode="ACCOUNT_BANNED", message="Account is banned.")
            
            case config.STATUS_CODES.get("blocked"):
                raise NoHarmException(statusCode=403, errorCode="ACCOUNT_BLOCKED", message="Account is blocked.")
            
            case config.STATUS_CODES.get("deleted"):
                raise NoHarmException(statusCode=404, errorCode="ACCOUNT_DELETED", message="Account is deleted.")


        _loginLimiter.onSuccess(_uuid)

        accessToken = _jwtHandler.createAccessToken(str(logged_user.id))
        refreshToken = _jwtHandler.createRefreshToken(str(logged_user.id))

        return {
            "accessToken": accessToken,
            "refreshToken": refreshToken,
            "tokenType": "Bearer"
        }


    def refresh(self, refreshToken: str) -> dict:
        """Issue a new token pair from a valid refresh token.

        Args:
            refreshToken: current valid refresh token

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

        # rotaciona: revoga o refresh token antigo (security.md §1.1)
        _jwtHandler.revokeToken(payload["jti"], payload["exp"])

        userId = payload["sub"]
        newAccessToken = _jwtHandler.createAccessToken(userId)
        newRefreshToken = _jwtHandler.createRefreshToken(userId)

        return {
            "accessToken": newAccessToken,
            "refreshToken": newRefreshToken,
            "tokenType": "Bearer"
        }


    def logout(self, accessToken: str, refreshToken: str) -> None:
        """Revoke both tokens, logging the user out of this device.

        Args:
            accessToken: current access token
            refreshToken: current refresh token
        """
        for token, tokenType in [(accessToken, "access"), (refreshToken, "refresh")]:
            payload = _jwtHandler.verifyToken(token, tokenType)
            if payload:
                _jwtHandler.revokeToken(payload["jti"], payload["exp"])