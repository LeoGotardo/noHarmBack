from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class FriendshipBase(BaseModel):
    sender: UUID = Field(..., description="User ID")
    reciver: UUID = Field(..., description="User ID")
    sendAt: datetime = Field(..., description="Start time")
    recivedAt: datetime = Field(..., description="End time")
    status: int = Field(default=1, description="Friendship status (ex: 1 active, 0 disabled)")


class FriendshipCreate(FriendshipBase):
    pass


class FriendshipUpdate(FriendshipBase):
    sendAt: Optional[datetime] = Field(None, description="Start time")
    recivedAt: Optional[datetime] = Field(None, description="End time")
    status: Optional[int] = Field(None, description="Friendship status (ex: 1 active, 0 disabled)")

class FriendshipResponse(FriendshipBase):
    id: UUID
    createdAt: datetime = Field(..., description="Start time")
    updatedAt: datetime = Field(..., description="End time")


class FriendshipListResponse(BaseModel):
    friendships: list[FriendshipResponse]
    total: int