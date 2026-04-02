from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID

from datetime import datetime

class AuthBase(BaseModel):
    type: int = Field(..., description="Auth type (ex: 1 register, 2 login, 3 refresh, 4 logout)")
    createdAt: datetime = Field(..., description="Start time")
    updatedAt: datetime = Field(..., description="End time")
    
    
class AuthCreate(AuthBase):
    pass

    
class AuthUpdate(AuthBase):
    type: Optional[int] = Field(None, description="Auth type (ex: 1 register, 2 login, 3 refresh, 4 logout)")
    createdAt: Optional[datetime] = Field(None, description="Start time")
    updatedAt: Optional[datetime] = Field(None, description="End time")
    
    
class AuthResponse(AuthBase):
    id: UUID
    createdAt: datetime
    updatedAt: datetime
    
    class Config:
        # Allow Pydantic to user ORM fields (como o UserModel do SQLAlchemy)
        from_attributes = True
        
        
class AuthListResponse(BaseModel):
    auths: list[AuthResponse]
    total: int


class AuthRegisterRequest(AuthBase):
    id: UUID = Field(default=None, description="User ID")
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(min_length=3, max_length=50)
    profile_picture: str = Field(default=None, description="Profile picture URL")
    
    
class AuthLoginRequest(AuthBase):
    email: str = Field(min_length=3, max_length=50)
    
    
class AuthRefreshRequest(AuthBase):
    refreshToken: str = Field(min_length=3, max_length=50)
    
    
class AuthLogoutRequest(AuthBase):
    accessToken: str = Field(min_length=3, max_length=50)
    refreshToken: str = Field(min_length=3, max_length=50)