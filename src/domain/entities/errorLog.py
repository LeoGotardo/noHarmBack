from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class ErrorLog:
    """One distinct fault, with how often and how recently it happened.

    `count` and `last_seen` are what make this a fault rather than an
    occurrence: the same crash four thousand times is one row here.
    """
    id: Optional[UUID] = None
    kind: str = "unhandled"
    path: str = ""
    method: str = ""
    fingerprint: str = ""
    exception_type: str = ""
    status_code: int = 500
    last_seen: Optional[datetime] = None
    count: int = 1
    message: Optional[str] = None
    traceback: Optional[str] = None
    user_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class HostAccess:
    """A login to the machine itself, as the host's SSH log reported it."""
    id: Optional[UUID] = None
    occurred_at: Optional[datetime] = None
    os_user: str = ""
    source_ip: str = ""
    method: str = ""
    result: str = "accepted"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
