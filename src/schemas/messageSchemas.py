from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class MessageCreate(BaseModel):
    chat: UUID = Field(..., description="Chat ID")
    sender: UUID = Field(..., description="Sender user ID")
    message: str = Field(..., description="Message content")
    status: int = Field(default=7, description="Message status")


class MessageUpdate(BaseModel):
    message: Optional[str] = Field(None, description="Message content")
    status: Optional[int] = Field(None, description="Message status")


class MessageResponse(BaseModel):
    id: UUID
    chat: UUID = Field(..., description="Chat ID")
    sender: UUID = Field(..., description="Sender user ID")
    message: str = Field(..., description="Message content")
    status: int = Field(..., description="Message status")
    send_at: Optional[datetime] = Field(None, description="Sent time")
    recived_at: Optional[datetime] = Field(None, description="Received time")
    created_at: datetime = Field(..., description="Created time")
    updated_at: datetime = Field(..., description="Updated time")

    model_config = ConfigDict(from_attributes=True)


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    total: int
