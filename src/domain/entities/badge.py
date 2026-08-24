from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from uuid import UUID

@dataclass
class Badge:
    name: str
    description: str
    milestone: int  # clean days required to earn the badge
    icon: str
    status: int
    id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None