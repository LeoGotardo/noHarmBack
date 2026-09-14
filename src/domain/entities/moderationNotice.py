from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class ModerationNotice:
    """A moderator telling a user what was decided about their account.

    `kind` is `warning` (nothing changed) or `suspension` (written beside the
    ban, so the account is not left guessing when it comes back).
    """
    user_id: str
    kind: str
    reason: str
    message: Optional[str] = None
    issued_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id: Optional[UUID] = None
