from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class StreakResponse(BaseModel):
    id: UUID
    owner: UUID = Field(..., description="Owner user ID")
    start: Optional[datetime] = Field(None, description="Start time")
    end: Optional[datetime] = Field(None, description="End time")
    status: int = Field(..., description="Streak status")
    isRecord: bool = Field(..., description="Whether this is the user's personal record")
    createdAt: Optional[datetime] = Field(None, description="Created at")

    class Config:
        from_attributes = True


class StreakListResponse(BaseModel):
    streaks: list[StreakResponse]
    total: int


# Kept for backward compatibility with any internal callers
class StreakCreate(BaseModel):
    owner: UUID
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    status: int = 1
    isRecord: bool = False


class StreakUpdate(BaseModel):
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    status: Optional[int] = None
    isRecord: Optional[bool] = None
