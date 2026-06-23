from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

@dataclass
class Streak:
    owner_id: str
    start_at: datetime
    status: int
    id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    is_record: Optional[bool] = False
    end_at: Optional[datetime] = None
    last_checkin: Optional[datetime] = None
