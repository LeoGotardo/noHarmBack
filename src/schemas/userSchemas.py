from pydantic import BaseModel, ConfigDict, Field
from schemas.types import Email
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    """
    Schema base for the commun fields of the User.
    """
    username: str = Field(..., min_length=3, max_length=50, description="Unique username")
    email: Email = Field(..., description="Valid email address")
    status: int = Field(default=1, description="Account status (ex: 1 enabled, 0 disabled)")

class UserCreate(UserBase):
    """
    Creation schema for a new user.
    All fields are optional here.
    """
    profile_picture: Optional[str] = Field(None, description="Profile picture in binary format")

class UserUpdate(BaseModel):
    """
    Schema for update user.
    All fields are optional here.
    """
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[Email] = None
    status: Optional[int] = None
    profile_picture: Optional[str] = None
    
class ProfileUpdateRequest(BaseModel):
    username: Optional[str] = None
    profile_picture: Optional[str] = None

class UserResponse(UserBase):
    """
    Schema for the client response.
    Has the fields created by the database (ID and timestamps).
    """
    id: str
    profile_picture: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class UserStatsResponse(BaseModel):
    """Public activity numbers for a profile other than your own.

    Visible to friends only: the screen offers "Add to see activity", and a
    streak is recovery data, not a public counter. For everyone else the fields
    come back None and the UI keeps showing its placeholder.
    """
    visible: bool = Field(..., description="False when the viewer is not a friend")
    day_streak: Optional[int] = Field(None, description="Days of the active streak, or 0 when there is none")
    badges_earned: Optional[int] = Field(None, description="How many badges the user holds")


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
