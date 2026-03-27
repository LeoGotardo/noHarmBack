from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from src.schemas.userSchemas import UserResponse


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
    
    class Config:
        # Allow Pydantic to user ORM fields (como o UserModel do SQLAlchemy)
        from_attributes = True
        
        
class UserBadgeListResponse(BaseModel):
    badges: list[UserBadgeResponse]
    total: int