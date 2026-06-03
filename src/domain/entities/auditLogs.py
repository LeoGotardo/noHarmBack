from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

@dataclass
class AuditLogs:
    type: int
    description: str
    id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    catalyst_id: Optional[UUID] = None
    catalyst: Optional[int] = None
