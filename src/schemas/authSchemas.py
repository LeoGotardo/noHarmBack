from pydantic import BaseModel, ConfigDict, EmailStr, Field
from typing import Optional


class AuthRegisterRequest(BaseModel):
    uid: str = Field(..., description="Firebase UID")
    email: EmailStr = Field(..., description="User email")
    username: str = Field(..., min_length=3, max_length=50, description="Username (alphanumeric, _ and - only)")
    photoURL: Optional[str] = Field(None, description="Profile picture URL from Firebase")
    emailVerified: bool = Field(default=False, description="Whether Firebase confirmed email")


class AuthLoginRequest(BaseModel):
    uid: str = Field(..., description="Firebase UID")
    email: EmailStr = Field(..., description="User email")


class AuthRefreshRequest(BaseModel):
    refreshToken: str = Field(..., description="Valid refresh token")


class AuthResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "Bearer"

    model_config = ConfigDict(from_attributes=True)
