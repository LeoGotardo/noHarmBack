from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

@dataclass
class UserBadge:
    user_id: UUID
    badge_id: UUID
    status: int
    id: Optional[UUID] = None
    given_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None