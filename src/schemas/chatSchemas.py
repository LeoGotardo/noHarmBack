from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional
from schemas.messageSchemas import MessageListResponse
from uuid import UUID


class ChatBase(BaseModel):
    sender: UUID = Field(..., description="User ID")
    reciver: UUID = Field(..., description="User ID")
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
    messages: MessageListResponse

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ChatListResponse(BaseModel):
    chats: list[ChatResponse]
    total: int
