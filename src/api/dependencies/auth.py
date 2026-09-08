from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core.config import config
from core.database import database
from infrastructure.database.models.userModel import UserModel
from infrastructure.database.rlsContext import RLSContext
from security.jwtHandler import JwtHandler
from security.tokenBlacklist import TokenBlacklist

security = HTTPBearer()
TokenBlacklist = TokenBlacklist()
jwtHandler = JwtHandler(TokenBlacklist)

# Accounts in these states must not be able to use a still-valid access token
# (§1.4). A signature check alone let deleted accounts keep reading their data
# for the remaining lifetime of every issued token.
_REJECTED_STATUSES = {
    config.STATUS_CODES["deleted"],
    config.STATUS_CODES["banned"],
    config.STATUS_CODES["blocked"],
}

_STATUS_ERRORS = {
    config.STATUS_CODES["deleted"]: ("ACCOUNT_DELETED", "Account not found."),
    config.STATUS_CODES["banned"]:  ("ACCOUNT_BANNED", "Account is banned."),
    config.STATUS_CODES["blocked"]: ("ACCOUNT_BLOCKED", "Account is blocked."),
}


def getAccountStatus(userId: str) -> int | None:
    """Read a user's current status, or None when the row is gone."""
    session = database.session
    try:
        RLSContext.setUserId(session, userId)
        return session.query(UserModel.status).filter(UserModel.id == userId).scalar()
    finally:
        session.close()


def getCurrentUser(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    payload = jwtHandler.verifyToken(credentials.credentials, "access")

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    userId = payload["sub"]
    status = getAccountStatus(userId)

    if status is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token.")

    if status in _REJECTED_STATUSES:
        _, message = _STATUS_ERRORS[status]
        raise HTTPException(status_code=403, detail=message)

    return userId


def getAdminUser(userId: str = Depends(getCurrentUser)) -> str:
    """Authorise an admin-only endpoint.

    There is no role column and no admin UI: authorisation is the
    `ADMIN_USER_IDS` allowlist and nothing else. It defaults to empty, so an
    environment that has named no administrators rejects every admin call
    rather than falling open.

    This matters more than it looks. `PUT /users/{id}/status/{status}` can set
    any account to any status — it is the only way to ban someone, and equally
    the only way to *unban* someone. Behind `getCurrentUser` alone, any signed-in
    user could lift their own ban, or ban anyone else, which left every
    "banned accounts cannot sign in" rule in the codebase decorative.

    Returns 404 rather than 403 for a non-admin: whether an admin surface exists
    here is not something an ordinary caller needs confirmed.
    """
    if userId not in config.ADMIN_USER_IDS:
        raise HTTPException(status_code=404, detail="Not found.")

    return userId
