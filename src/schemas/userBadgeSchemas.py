from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class UserBadgeBase(BaseModel):
    user_id: str = Field(..., description="User ID")
    badge_id: UUID = Field(..., description="Badge ID")
    given_at: Optional[datetime] = Field(None, description="Granted at")
    status: int = Field(default=1, description="Badge status (ex: 1 active, 0 disabled)")


class UserBadgeCreate(UserBadgeBase):
    pass


class UserBadgeUpdate(BaseModel):
    given_at: Optional[datetime] = Field(None, description="Granted at")
    status: Optional[int] = Field(None, description="Badge status (ex: 1 active, 0 disabled)")


class UserBadgeResponse(UserBadgeBase):
    id: UUID
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class UserBadgeListResponse(BaseModel):
    badges: list[UserBadgeResponse]
    total: int
