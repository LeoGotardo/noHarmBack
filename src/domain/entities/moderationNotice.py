from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class ModerationNotice:
    """A moderator telling a user what was decided about their account.

    `kind` is `warning` (nothing changed), `suspension` (written beside the
    ban, so the account is not left guessing when it comes back), `rename`,
    `picture`, or `post_removed` / `comment_removed` (something the user wrote
    was taken off the Community tab — `excerpt` says what).
    """
    user_id: str
    kind: str
    reason: str
    message: Optional[str] = None
    issued_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    # The start of the removed post or comment, for `post_removed` and
    # `comment_removed`. None for every other kind.
    excerpt: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id: Optional[UUID] = None
