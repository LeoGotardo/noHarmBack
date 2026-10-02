from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone


class StreakResponse(BaseModel):
    id: UUID
    owner_id: str = Field(..., description="Owner user ID")
    start_at: datetime = Field(..., description="When the streak started")
    end_at: Optional[datetime] = Field(None, description="When the streak ended (null if active)")
    last_checkin: Optional[datetime] = Field(None, description="Last sobriety check-in timestamp")
    status: int = Field(..., description="Streak status")
    is_record: Optional[bool] = Field(False, description="Whether this is the user's personal record")
    created_at: Optional[datetime] = Field(None, description="Created at")
    updated_at: Optional[datetime] = Field(None, description="Updated at")

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @field_validator("start_at", "end_at", "last_checkin", "created_at", "updated_at")
    @classmethod
    def _tagUtc(cls, value: Optional[datetime]) -> Optional[datetime]:
        # Encrypted DateTime columns decrypt naive values without an offset, and
        # a timestamp with no offset is parsed as *local* time by JavaScript, so
        # the client's clock ran hours apart from the server's day count. Naive
        # values are stored in UTC (see StreakService._asUtc), so tag them.
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class StreakListResponse(BaseModel):
    streaks: list[StreakResponse]
    total: int


class StreakStartRequest(BaseModel):
    start_at: Optional[datetime] = Field(None, description="When the streak started (defaults to now)")

    model_config = ConfigDict(extra="forbid")


class StreakEndRequest(BaseModel):
    end_at: Optional[datetime] = Field(None, description="When the streak ended (defaults to now)")

    model_config = ConfigDict(extra="forbid")


class StreakCreate(BaseModel):
    owner_id: str
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
