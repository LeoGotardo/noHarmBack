from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class Report:
    """A user reporting another user's behaviour to the moderators.

    `reporter` and `reported` are both optional because the row outlives both
    accounts: purging either sets its column to NULL rather than destroying the
    moderation record (migrations 20260909_01 and 20260911_01).

    `reported_uid` is the copy that does not go away — it is what the duplicate
    check and the per-account counts read, so they keep answering after the
    account is gone. `reported_username` is the display name at filing time.
    """
    reason: str
    status: int
    reported_uid: Optional[str] = None
    reported_username: Optional[str] = None
    reported: Optional[str] = None
    reporter: Optional[str] = None
    details: Optional[str] = None
    # Who is reviewing it, and since when. A lock older than
    # `REPORT_LOCK_MINUTES` counts as released — see `Report.isLockedBySomeoneElse`.
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    # `chat`, `post`, `comment` or None — where the report was filed from.
    target_kind: Optional[str] = None
    # Not stored. True only on the answer to a filing that added evidence to
    # this reporter's already-open report about the same person instead of
    # opening a second one (D8 in docs/POSTS_PLAN.md).
    appended: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id: Optional[UUID] = None
