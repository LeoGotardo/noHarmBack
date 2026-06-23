from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime


class NotificationResponse(BaseModel):
    id: UUID
    user_id: str
    status: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    total: int
