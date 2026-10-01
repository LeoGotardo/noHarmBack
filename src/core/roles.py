"""Who is an administrator, and the mark shown beside a user's name.

Three sources decide it:

- `OFFICIAL_USER_IDS` (config) — NoHarm's own accounts. They can do everything
  an administrator can, and they are the only ones who can promote and demote.
- `ADMIN_USER_IDS` (config) — administrators named by the environment. This is
  how the first one exists, and the app cannot revoke them.
- `tb_19` — administrators an official account promoted from inside the app.

An account that is both reads as official — the app speaking outranks the
person who happens to run it.

`isAdmin` authorises and reads tb_19 on every call, so a demotion takes effect
on the next request. `publicRole` is display only and reads a short-lived copy,
because it runs once per user in every list the API returns.
"""
import logging
import time
from typing import Annotated, Literal, Optional

from pydantic import BeforeValidator

from core.config import config
from core.database import database

logger = logging.getLogger(__name__)

PublicRole = Literal["official", "admin"]

# The field type for schemas. Whatever arrives as input is dropped — a client's
# claim, or an ORM row's stray attribute — and the schema's after-validator
# fills it from `publicRole`. A real field and not a computed one because
# FastAPI re-validates the dumped model, and `extra="forbid"` would refuse the
# key it had just written.
RoleField = Annotated[Optional[PublicRole], BeforeValidator(lambda _v: None)]

# How long the display copy of tb_19 is trusted. Another worker's promotion
# shows up in the mark within this window; authorisation never waits on it.
_GRANTS_TTL_SECONDS = 30
_grantsCache: tuple[float, frozenset[str]] = (0.0, frozenset())


def _readGrants() -> frozenset[str]:
    from infrastructure.database.models.adminGrantModel import AdminGrantModel

    session = database.session
    try:
        return frozenset(str(uid) for (uid,) in session.query(AdminGrantModel.user_id).all())
    finally:
        session.close()


def grantedAdminIds(fresh: bool = False) -> frozenset[str]:
    """The uids in tb_19.

    `fresh` reads the table now and is what authorisation uses; a failed fresh
    read answers empty, so an outage denies rather than trusting an old copy.
    Otherwise a failed read keeps the previous copy and is not retried until the
    TTL runs out again — a database that is down must not cost one connection
    attempt per user in every list.
    """
    global _grantsCache
    loadedAt, ids = _grantsCache
    if fresh or time.monotonic() - loadedAt > _GRANTS_TTL_SECONDS:
        try:
            ids = _readGrants()
        except Exception:
            logger.exception("could not read admin grants")
            if fresh:
                return frozenset()
        _grantsCache = (time.monotonic(), ids)
    return ids


def invalidateGrants() -> None:
    """Drop this worker's copy — called after a promotion or demotion."""
    global _grantsCache
    _grantsCache = (0.0, frozenset())


def isOfficial(userId) -> bool:
    """Whether `userId` is one of NoHarm's own accounts.

    Unlike the mark, this one *does* authorise: an official account may write
    to anyone (and to everyone, through the broadcast), nobody may write back
    into a conversation with it, and it alone promotes administrators. See
    ChatService, MessageService and the /admin/admins routes.
    """
    return str(userId) in config.OFFICIAL_USER_IDS


def isEnvAdmin(userId) -> bool:
    return str(userId) in config.ADMIN_USER_IDS


def isAdmin(userId) -> bool:
    """Whether `userId` may use the admin and moderation routes. Authorises."""
    uid = str(userId)
    if isOfficial(uid) or isEnvAdmin(uid):
        return True
    return uid in grantedAdminIds(fresh=True)


def allAdminIds() -> set[str]:
    """Everyone `isAdmin` would let in — the audience for admin alerts."""
    return (
        set(map(str, config.OFFICIAL_USER_IDS))
        | set(map(str, config.ADMIN_USER_IDS))
        | set(grantedAdminIds())
    )


def publicRole(userId) -> Optional[PublicRole]:
    uid = str(userId)
    if isOfficial(uid):
        return "official"
    if isEnvAdmin(uid) or uid in grantedAdminIds():
        return "admin"
    return None
