"""The mark shown beside a user's name, and who gets which.

Two allowlists decide it, both in config: `OFFICIAL_USER_IDS` (NoHarm's own
accounts) and `ADMIN_USER_IDS` (moderators). An account on both reads as
official — the app speaking outranks the person who happens to run it.

The mark is display only. Authorisation stays with `getAdminUser`, which reads
the allowlist itself and never this value.
"""
from typing import Annotated, Literal, Optional

from pydantic import BeforeValidator

from core.config import config

PublicRole = Literal["official", "admin"]

# The field type for schemas. Whatever arrives as input is dropped — a client's
# claim, or an ORM row's stray attribute — and the schema's after-validator
# fills it from `publicRole`. A real field and not a computed one because
# FastAPI re-validates the dumped model, and `extra="forbid"` would refuse the
# key it had just written.
RoleField = Annotated[Optional[PublicRole], BeforeValidator(lambda _v: None)]


def publicRole(userId) -> Optional[PublicRole]:
    uid = str(userId)
    if uid in config.OFFICIAL_USER_IDS:
        return "official"
    if uid in config.ADMIN_USER_IDS:
        return "admin"
    return None


def isOfficial(userId) -> bool:
    """Whether `userId` is one of NoHarm's own accounts.

    Unlike the mark, this one *does* authorise: an official account may write
    to anyone (and to everyone, through the broadcast), and nobody may write
    back into a conversation with it. See ChatService and MessageService.
    """
    return str(userId) in config.OFFICIAL_USER_IDS
