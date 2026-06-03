from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class StreakResponse(BaseModel):
    id: UUID
    owner_id: UUID = Field(..., description="Owner user ID")
    start: datetime = Field(..., description="Start time")
    end: Optional[datetime] = Field(None, description="End time")
    status: int = Field(..., description="Streak status")
    is_record: Optional[bool] = Field(False, description="Whether this is the user's personal record")
    created_at: Optional[datetime] = Field(None, description="Created at")
    updated_at: Optional[datetime] = Field(None, description="Updated at")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class StreakListResponse(BaseModel):
    streaks: list[StreakResponse]
    total: int


class StreakCreate(BaseModel):
    owner_id: UUID
    start: datetime
    end: Optional[datetime] = None
    status: int = 1
    is_record: bool = False


class StreakUpdate(BaseModel):
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    status: Optional[int] = None
    is_record: Optional[bool] = None
