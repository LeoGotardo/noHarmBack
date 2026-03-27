from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from src.schemas.chatSchemas import ChatResponse
from src.schemas.userSchemas import UserResponse


class MessageBase(BaseModel):
    chat: ChatResponse = Field(..., description="Chat ID")
    sender: UserResponse = Field(..., description="User ID")
    message: str = Field(..., description="Message content")
    status: int = Field(default=1, description="Message status (ex: 1 active, 0 disabled)")
    sendAt: datetime = Field(..., description="Start time")
    recivedAt: datetime = Field(None, description="End time")


class MessageCreate(MessageBase):
    recivedAt: Optional[datetime] = Field(None, description="End time")


class MessageUpdate(MessageBase):
    sendAt: Optional[datetime] = Field(None, description="Start time")
    recivedAt: Optional[datetime] = Field(None, description="End time")
    status: Optional[int] = Field(None, description="Message status (ex: 1 active, 0 disabled)")


class MessageResponse(MessageBase):
    id: UUID
    createdAt: datetime = Field(..., description="Start time")
    updatedAt: datetime = Field(..., description="End time")
    
    class Config:
        # Allow Pydantic to user ORM fields (como o UserModel do SQLAlchemy)
        from_attributes = True


class MessageListResponse(BaseModel):
    messages: list[MessageResponse]
    total: int