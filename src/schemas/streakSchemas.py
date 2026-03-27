from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from src.schemas.userSchemas import UserResponse

class StreakBase(BaseModel):
    owner: UserResponse = Field(..., description="User ID")
    start: datetime = Field(..., description="Start time")
    end: datetime = Field(None, description="End time")
    status: int = Field(default=1, description="Streak status (ex: 1 active, 0 disabled)")
    isRecord: bool = Field(default=False, description="Record status (ex: True, False)")
    
    
class StreakCreate(StreakBase):
    pass

class StreakUpdate(StreakBase):
    start: Optional[datetime] = Field(None, description="Start time")
    end: Optional[datetime] = Field(None, description="End time")
    status: Optional[int] = Field(None, description="Streak status (ex: 1 active, 0 disabled)")
    isRecord: Optional[bool] = Field(None, description="Record status (ex: True, False)")
    
    
class StreakResponse(StreakBase):
    id: UUID
    createdAt: datetime = Field(..., description="Start time")
    updatedAt: datetime = Field(..., description="End time")
    
    class Config:
        # Allow Pydantic to user ORM fields (como o UserModel do SQLAlchemy)
        from_attributes = True
        
        
class StreakListResponse(BaseModel):
    streaks: list[StreakResponse]    
    total: int