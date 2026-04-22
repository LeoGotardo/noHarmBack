from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class ChatBase(BaseModel):
    sender: UUID = Field(..., description="User ID")
    reciver: UUID = Field(..., description="User ID")
    startedAt: datetime = Field(..., description="Start time")
    endedAt: datetime = Field(None, description="End time")
    status: int = Field(default=1, description="Chat status (ex: 1 active, 0 disabled)")
    

class ChatCreate(ChatBase):
    pass


class ChatUpdate(ChatBase):
    endedAt: Optional[datetime] = Field(None, description="End time")
    status: Optional[int] = Field(None, description="Chat status (ex: 1 active, 0 disabled)")
    
    
class ChatResponse(ChatBase):
    id: UUID
    createdAt: datetime = Field(..., description="Start time")
    updatedAt: datetime = Field(..., description="End time")
    
    model_config = ConfigDict(from_attributes=True)
        
        
class ChatListResponse(BaseModel):
    chats: list[ChatResponse]
    total: int