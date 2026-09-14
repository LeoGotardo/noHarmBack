from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class User:
    id: str
    username: str
    email: str
    status: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    profile_picture: Optional[str] = None
    # Set when the account is soft-deleted; the purge job destroys the row
    # ACCOUNT_DELETION_GRACE_DAYS after this instant.
    deleted_at: Optional[datetime] = None
    # When a suspension ends. NULL while `status` is anything but banned, and
    # NULL for a permanent ban too — a date is what makes a ban temporary.
    banned_until: Optional[datetime] = None
