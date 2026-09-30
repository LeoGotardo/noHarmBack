from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated, Literal, Optional
from uuid import UUID
from datetime import datetime

from schemas.friendshipSchemas import FriendUserInfo
from schemas.noticeSchemas import NoticeReason


# Trimmed before the length is checked, so "   " is a 422 and not a post, and a
# 1000-character post padded with newlines is not refused for the padding.
PostContent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
CommentContent = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]

PostVisibility = Literal["community", "friends"]


# ── requests ──────────────────────────────────────────────────────────────────

class PostCreateRequest(BaseModel):
    content: PostContent = Field(..., description="The post, 1–1000 characters after trimming. Text only")
    visibility: PostVisibility = Field(
        ...,
        description="`friends` — accepted friends only · `community` — every signed-in user"
    )

    model_config = ConfigDict(extra="forbid")


class CommentCreateRequest(BaseModel):
    content: CommentContent = Field(..., description="The comment, 1–500 characters after trimming")

    model_config = ConfigDict(extra="forbid")


class RemoveContentRequest(BaseModel):
    """A moderator taking a post or comment down.

    `self_harm` is allowed here, unlike on a warning: taking a crisis post off a
    public feed can be the right call. It is still never a telling-off — the
    notice the author gets says what was removed, not who asked.
    """
    reason: NoticeReason = Field(..., description="The conduct being named")
    message: Optional[str] = Field(None, max_length=500, description="The moderator's own words, shown to the author")
    reportId: Optional[UUID] = Field(None, description="The report this acts on, for the audit trail")

    model_config = ConfigDict(extra="forbid")


# ── responses ─────────────────────────────────────────────────────────────────

class PostResponse(BaseModel):
    id: UUID
    author: FriendUserInfo = Field(..., description="Who wrote it — the same shape as a friend")
    content: str
    visibility: PostVisibility
    like_count: int = Field(..., description="Likes from enabled accounts. The same for every viewer")
    comment_count: int = Field(..., description="Live comments from enabled accounts. The same for every viewer")
    liked_by_me: bool
    is_mine: bool
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class PostPageResponse(BaseModel):
    posts: list[PostResponse]
    next_cursor: Optional[str] = Field(None, description="Pass back as `cursor` for the next page; null on the last")


class CommentResponse(BaseModel):
    id: UUID
    post_id: UUID
    author: FriendUserInfo
    content: str
    is_mine: bool
    can_delete: bool = Field(..., description="My comment, or a comment on my post")
    created_at: datetime

    model_config = ConfigDict(extra="forbid")


class CommentPageResponse(BaseModel):
    comments: list[CommentResponse]
    next_cursor: Optional[str] = None


class LikeResponse(BaseModel):
    liked: bool
    like_count: int


class ModeratedContentResponse(BaseModel):
    """What a moderator gets back from removing or restoring something.

    Deliberately not the content: the moderator already read it in the
    report's evidence, and this answers only "what state is it in now".
    """
    id: UUID
    kind: Literal["post", "comment"]
    author_id: str
    status: int = Field(..., description="1 up · 3 removed by moderation")
    removed_at: Optional[datetime] = None
