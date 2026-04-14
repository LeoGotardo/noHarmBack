from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class UserBase(BaseModel):
    """
    Schema base for the commun fields of the User.
    """
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: EmailStr = Field(..., description="Valid email address")
    status: int = Field(default=1, description="Account status (ex: 1 enabled, 0 disabled)")

class UserCreate(UserBase):
    """
    Creation schema for a new user.
    All fields are optional here.
    """
    profile_picture: Optional[bytes] = Field(None, description="Profile picture in binary format")

class UserUpdate(BaseModel):
    """
    Schema for update user.
    All fields are optional here.
    """
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[EmailStr] = None
    status: Optional[int] = None
    profile_picture: Optional[bytes] = None

class UserResponse(UserBase):
    """
    Schema for the client response.
    Has the fields created by the database (ID and timestamps).
    """
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        # Allow Pydantic to user ORM fields (como o UserModel do SQLAlchemy)
        from_attributes = True


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
