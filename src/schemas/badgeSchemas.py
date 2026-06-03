
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID

from datetime import datetime

class BadgeBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    description: str = Field(..., min_length=3, max_length=500)
    milestone: datetime = Field(..., description="Milestone date")
    status: int = Field(default=1, description="Badge status (ex: 1 active, 0 inactive)")
    icon: str = Field(..., description="Icon image link")
    updated_at: datetime = Field(..., description="Last updated timestamp")
    
    
class BadgeCreate(BadgeBase):
    created_at: datetime = Field(..., description="Created timestamp")

    
class BadgeUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=50)
    description: Optional[str] = Field(None, min_length=3, max_length=500)
    milestone: Optional[datetime] = Field(None, description="Milestone date")
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