from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class StreakResponse(BaseModel):
    id: UUID
    owner_id: UUID = Field(..., description="Owner user ID")
    start_at: datetime = Field(..., description="When the streak started")
    end_at: Optional[datetime] = Field(None, description="When the streak ended (null if active)")
    last_checkin: Optional[datetime] = Field(None, description="Last sobriety check-in timestamp")
    status: int = Field(..., description="Streak status")
    is_record: Optional[bool] = Field(False, description="Whether this is the user's personal record")
    created_at: Optional[datetime] = Field(None, description="Created at")
    updated_at: Optional[datetime] = Field(None, description="Updated at")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class StreakListResponse(BaseModel):
    streaks: list[StreakResponse]
    total: int


class StreakStartRequest(BaseModel):
    start_at: Optional[datetime] = Field(None, description="When the streak started (defaults to now)")


class StreakEndRequest(BaseModel):
    end_at: Optional[datetime] = Field(None, description="When the streak ended (defaults to now)")


class StreakCreate(BaseModel):
    owner_id: UUID
    start_at: datetime
    end_at: Optional[datetime] = None
    last_checkin: Optional[datetime] = None
    status: int = 1
    is_record: bool = False


class StreakUpdate(BaseModel):
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    last_checkin: Optional[datetime] = None
    status: Optional[int] = None
    is_record: Optional[bool] = None
