from dataclasses import dataclass
from datetime import date, datetime
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
    # Set by moderation when a username had to go. The account keeps working;
    # it just cannot be used until a new name is chosen.
    must_change_username: bool = False
    # Set by moderation when a picture had to go. Blocks the Google sync too,
    # or the photo returns at the next sign-in.
    picture_blocked: bool = False
    # Declared at registration, self-reported. None for every account created
    # before the field existed — absent is not "under age", it is "never
    # asked", and the two must not be read as the same thing.
    birth_date: Optional[date] = None
