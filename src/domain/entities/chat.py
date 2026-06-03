from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

@dataclass
class Chat:
    sender: UUID
    reciver: UUID
    started_at: datetime
    status: int
    id: Optional[UUID] = None
    ended_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    messages: list = field(default_factory=list)
