from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class FriendshipBase(BaseModel):
    sender: UUID = Field(..., description="User ID")
    reciver: UUID = Field(..., description="User ID")
    send_at: Optional[datetime] = Field(None, description="Sent at")
    recived_at: Optional[datetime] = Field(None, description="Received at")
    status: int = Field(default=1, description="Friendship status (ex: 1 active, 0 disabled)")


class FriendshipCreate(FriendshipBase):
    pass


class FriendshipUpdate(BaseModel):
    send_at: Optional[datetime] = Field(None, description="Sent at")
    recived_at: Optional[datetime] = Field(None, description="Received at")
    status: Optional[int] = Field(None, description="Friendship status (ex: 1 active, 0 disabled)")


class FriendshipResponse(FriendshipBase):
    id: UUID
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class FriendshipListResponse(BaseModel):
    friendships: list[FriendshipResponse]
    total: int
