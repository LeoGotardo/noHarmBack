from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional
from uuid import UUID
from schemas.messageSchemas import MessageResponse


class ChatBase(BaseModel):
    sender: str = Field(..., description="User ID")
    reciver: str = Field(..., description="User ID")
    started_at: datetime = Field(..., description="Start time")
    ended_at: Optional[datetime] = Field(None, description="End time")
    status: int = Field(default=1, description="Chat status (ex: 1 active, 0 disabled)")


class ChatCreate(ChatBase):
    pass


class ChatUpdate(BaseModel):
    ended_at: Optional[datetime] = Field(None, description="End time")
    status: Optional[int] = Field(None, description="Chat status (ex: 1 active, 0 disabled)")


class ChatResponse(ChatBase):
    id: UUID
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")
    last_message: Optional[MessageResponse] = Field(None, description="Most recent message in the chat")
    unread_count: int = Field(0, description="Unread messages addressed to the requesting user")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ChatListResponse(BaseModel):
    chats: list[ChatResponse]
    total: int
