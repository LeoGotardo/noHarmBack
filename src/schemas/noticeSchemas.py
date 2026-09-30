from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime


# The same closed set a report uses, `self_harm` included — and it is included
# on purpose. The service refuses that one with 400 `NOT_A_WARNING` and says
# why: a report about someone's safety is usually a frightened friend, and
# answering it with a telling-off is the worst available move. Leaving it out
# of the Literal would make the same call a bare 422 that teaches the caller
# nothing.
NoticeReason = Literal[
    "harassment",
    "spam",
    "inappropriate",
    "impersonation",
    "self_harm",
    "other",
]


class WarnRequest(BaseModel):
    """A warning: the rung between doing nothing and banning someone."""
    reason: NoticeReason = Field(..., description="The conduct being named")
    message: Optional[str] = Field(
        None,
        max_length=500,
        description=(
            "The moderator's own words, shown to the user. Never name the "
            "reporter here — the promise that they are not told is what makes "
            "reports fileable."
        )
    )

    model_config = ConfigDict(extra="forbid")


class NoticeResponse(BaseModel):
    id: UUID
    kind: str = Field(..., description="warning · suspension · rename · picture · post_removed · comment_removed")
    reason: str = Field(..., description="The conduct it names")
    message: Optional[str] = Field(None, description="The moderator's words, if any")
    excerpt: Optional[str] = Field(
        None,
        description="post_removed / comment_removed only: the start of what was removed"
    )
    acknowledged_at: Optional[datetime] = Field(None, description="When the user read it")
    created_at: datetime

    # `issued_by` and `user_id` are deliberately absent: the recipient does not
    # need the moderator's uid, and already knows whose account it is.
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class NoticeListResponse(BaseModel):
    notices: list[NoticeResponse]
    total: int
