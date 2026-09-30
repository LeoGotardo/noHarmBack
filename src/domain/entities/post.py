from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


# The two audiences an author can choose (D1). Stored as the string itself —
# the API exposes it as a string too, and a lookup table for two values would
# only be a place for the two to drift apart.
VISIBILITY_FRIENDS = "friends"
VISIBILITY_COMMUNITY = "community"
VISIBILITIES = (VISIBILITY_FRIENDS, VISIBILITY_COMMUNITY)


@dataclass
class Post:
    """Something a user wrote for the Community tab.

    `status` is `enabled` while it is up and `blocked` once a moderator removed
    it. There is no edit (D3): a post that changed after people answered it
    would change what their answers meant.
    """
    author_id: str
    content: str
    visibility: str
    status: int
    removed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id: Optional[UUID] = None


@dataclass
class PostComment:
    """A reply under a post. Same lifecycle as the post, one level down."""
    post_id: UUID
    author_id: str
    content: str
    status: int
    removed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id: Optional[UUID] = None
