from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID
from schemas.messageSchemas import MessageResponse
from core.roles import isOfficial


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
    # Derived from OFFICIAL_USER_IDS on every response, input discarded — the
    # same pattern as `RoleField`. True when either side is an official
    # account, which makes the conversation read-only for the other side.
    official: Annotated[bool, BeforeValidator(lambda _v: False)] = Field(
        False, description="One participant is an official NoHarm account; the other cannot reply"
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @model_validator(mode="after")
    def _fillOfficial(self):
        self.official = isOfficial(self.sender) or isOfficial(self.reciver)
        return self


class ChatListResponse(BaseModel):
    chats: list[ChatResponse]
    total: int
