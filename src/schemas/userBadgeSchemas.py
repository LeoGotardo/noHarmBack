from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from schemas.userSchemas import UserResponse


class UserBadgeBase(BaseModel):
    user: UserResponse = Field(..., description="User ID")
    badge: UUID = Field(..., description="Badge ID")
    givenAt: datetime = Field(..., description="Start time")
    status: int = Field(default=1, description="Badge status (ex: 1 active, 0 disabled)")


class UserBadgeCreate(UserBadgeBase):
    pass


class UserBadgeUpdate(UserBadgeBase):
    givenAt: Optional[datetime] = Field(None, description="Start time")
    status: Optional[int] = Field(None, description="Badge status (ex: 1 active, 0 disabled)")
    
    
class UserBadgeResponse(UserBadgeBase):
    id: UUID
    createdAt: datetime = Field(..., description="Start time")
    updatedAt: datetime = Field(..., description="End time")
    
    model_config = ConfigDict(from_attributes=True)
        
        
class UserBadgeListResponse(BaseModel):
    badges: list[UserBadgeResponse]
    total: int