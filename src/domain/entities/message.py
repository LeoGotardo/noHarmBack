from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

@dataclass
class Message:
    chat: UUID
    sender: UUID
    message: str
    status: int
    id: Optional[UUID] = None
    send_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    recived_at: Optional[datetime] = None