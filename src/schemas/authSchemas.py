from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class AuthRegisterRequest(BaseModel):
    # Identity comes from the token, never from the body: `uid`, `email` and
    # `emailVerified` used to be client-supplied, which made both invented
    # accounts and a bypass of email verification a matter of typing.
    idToken: str = Field(..., description="Firebase ID token from the sign-in flow")
    username: str = Field(..., min_length=3, max_length=50, description="Username (alphanumeric, _ and - only)")


class AuthLoginRequest(BaseModel):
    idToken: str = Field(..., description="Firebase ID token from the sign-in flow")


class AuthRefreshRequest(BaseModel):
    refreshToken: str = Field(..., description="Valid refresh token")


class AuthResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "Bearer"

    model_config = ConfigDict(from_attributes=True, extra="forbid")
