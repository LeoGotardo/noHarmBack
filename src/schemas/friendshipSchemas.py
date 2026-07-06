from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class FriendshipBase(BaseModel):
    sender: str = Field(..., description="User ID")
    reciver: str = Field(..., description="User ID")
    status: int = Field(default=1, description="Friendship status (ex: 1 active, 0 disabled)")


class FriendshipCreate(FriendshipBase):
    pass


class FriendshipUpdate(BaseModel):
    status: Optional[int] = Field(None, description="Friendship status (ex: 1 active, 0 disabled)")


class FriendUserInfo(BaseModel):
    id: str = Field(..., description="User ID")
    username: str = Field(..., description="User display name")
    profile_picture: Optional[str] = Field(None, description="Profile picture URL")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FriendshipResponse(FriendshipBase):
    id: UUID
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")
    sender_user: Optional[FriendUserInfo] = Field(None, description="Sender's public profile")
    reciver_user: Optional[FriendUserInfo] = Field(None, description="Receiver's public profile")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FriendshipListResponse(BaseModel):
    friendships: list[FriendshipResponse]
    total: int
