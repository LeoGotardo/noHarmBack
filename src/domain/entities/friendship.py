from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

@dataclass
class Friendship:
    sender: str
    reciver: str
    status: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id: Optional[UUID] = None
    # Who put the block on, when `status` is blocked. None for rows blocked
    # before migration 20261001_01, which keep the old either-side unblock.
    blocked_by: Optional[str] = None
