
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID

from datetime import datetime

class BadgeBase(BaseModel):
    """The fields a badge actually has, minus anything the server owns.

    `created_at` and `updated_at` used to live here, which made them required
    on the *request* too — `BadgeCreate` inherits this and `POST /badges`
    rejected every body without them. Nobody creating a badge can know those
    values, and letting a client supply them means letting it backdate one.
    `TimestampMixin` writes both, so they belong to the response alone.
    """

    name: str = Field(..., min_length=3, max_length=50)
    description: str = Field(..., min_length=3, max_length=500)
    milestone: int = Field(..., ge=0, description="Clean days required to earn the badge")
    status: int = Field(default=1, description="Badge status (ex: 1 active, 0 inactive)")
    icon: str = Field(..., description="Icon image link")


class BadgeCreate(BadgeBase):
    pass

    
class BadgeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    description: Optional[str] = Field(None, min_length=3, max_length=500)
    milestone: Optional[int] = Field(None, ge=0, description="Clean days required to earn the badge")
    status: Optional[int] = Field(None, description="Badge status (ex: 1 active, 0 inactive)")
    icon: Optional[str] = Field(None, description="Icon image link")
    
    
class BadgeResponse(BadgeBase):
    id : UUID
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class BadgeListResponse(BaseModel):
    badges: list[BadgeResponse]
    total: int