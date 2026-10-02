from infrastructure.database.repositories.adminGrantRepository import AdminGrantRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database
from core import roles

from datetime import timezone
from core.auditTypes import AuditType

_AUDIT_ADMIN_GRANTED = AuditType.ADMIN_GRANTED
_AUDIT_ADMIN_REVOKED = AuditType.ADMIN_REVOKED


class AdminGrantService:
    """Promoting and demoting administrators from inside the app.

    Only official accounts reach this (the routes' `getOfficialUser`). The
    allowlists in the environment are read, never written: an `env` or
    `official` administrator cannot be revoked here, and saying so with a 409
    is better than a demotion that silently does nothing.
    """

    def __init__(self, db: Database):
        self.grantRepository = AdminGrantRepository(db)
        self.userRepository = UserRepository(db)
        self.auditRepository = AuditLogsRepository(db)

    def _logAudit(self, actionType: int, catalystId: str, description: str) -> None:
        try:
            self.auditRepository.create(AuditLogsModel(
                type=actionType, catalyst_id=catalystId, catalyst=None, description=description
            ))
        except Exception:
            pass

    def _username(self, userId: str):
        try:
            return self.userRepository.findById(userId).username
        except NoHarmException:
            return None

    def listAdmins(self) -> list[dict]:
        rows: list[dict] = []
        seen: set[str] = set()

        for uid in map(str, config.OFFICIAL_USER_IDS):
            if uid not in seen:
                seen.add(uid)
                rows.append({"id": uid, "username": self._username(uid), "source": "official"})

        for uid in map(str, config.ADMIN_USER_IDS):
            if uid not in seen:
                seen.add(uid)
                rows.append({"id": uid, "username": self._username(uid), "source": "env"})

        for grant in self.grantRepository.findAll():
            uid = str(grant.user_id)
            if uid in seen:
                continue
            seen.add(uid)
            grantedAt = grant.created_at.replace(tzinfo=timezone.utc) if grant.created_at else None
            rows.append({
                "id": uid,
                "username": self._username(uid),
                "source": "granted",
                "granted_by": grant.granted_by,
                "granted_at": grantedAt,
            })

        return rows

    def promote(self, officialId: str, userId: str) -> None:
        user = self.userRepository.findById(userId)  # 404 when there is no such account

        if user.status != config.STATUS_CODES["enabled"]:
            raise NoHarmException(
                statusCode=409, errorCode="ACCOUNT_NOT_ACTIVE",
                message="Only an active account can be made an administrator."
            )
        if roles.isAdmin(userId):
            raise NoHarmException(
                statusCode=409, errorCode="ALREADY_ADMIN",
                message="This account is already an administrator."
            )

        self.grantRepository.grant(userId, officialId)
        roles.invalidateGrants()
        self._logAudit(_AUDIT_ADMIN_GRANTED, officialId, f"Admin granted to {userId}")

    def demote(self, officialId: str, userId: str) -> None:
        if roles.isOfficial(userId) or roles.isEnvAdmin(userId):
            raise NoHarmException(
                statusCode=409, errorCode="ADMIN_FROM_ENVIRONMENT",
                message="This administrator is set in the server configuration and cannot be removed from the app."
            )
        if not self.grantRepository.revoke(userId):
            raise NoHarmException(
                statusCode=404, errorCode="NOT_ADMIN",
                message="This account is not an administrator."
            )

        roles.invalidateGrants()
        self._logAudit(_AUDIT_ADMIN_REVOKED, officialId, f"Admin revoked from {userId}")
