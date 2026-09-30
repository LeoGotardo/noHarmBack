from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime


class BanCounts(BaseModel):
    """Banned accounts, split by whether the ban ends.

    `expired` is the one worth reading twice: a suspension lifts itself at the
    next sign-in, so these are accounts whose ban ran out and who have not come
    back since. Nothing is wrong with them — it is a measure of how many people
    did not return.
    """
    total: int
    permanent: int = Field(..., description="Banned with no end date")
    expired: int = Field(..., description="Past their end date and not signed in since")


class SanctionCounts(BaseModel):
    must_change_username: int
    picture_blocked: int
    both: int = Field(..., description="Carrying both — the account worth looking at")


class ConsentDebt(BaseModel):
    """Accounts that owe an answer on a document, and how many owe any.

    `any` is not the sum of the rest: an account behind on two documents is one
    account, and adding them would report more work than exists.
    """
    documents: dict[str, int] = Field(..., description="Accounts owing, per document")
    any: int


class AccountPanel(BaseModel):
    by_status: dict[str, int] = Field(..., description="Accounts per status name")
    created: dict[str, int] = Field(..., description="Sign-ups per window, in days; cumulative")
    bans: BanCounts
    sanctions: SanctionCounts
    consent_debt: ConsentDebt


class ModerationPanel(BaseModel):
    queue: dict[str, int] = Field(..., description="open · actioned · dismissed")
    open_by_reason: dict[str, int]
    self_harm_open: int = Field(
        ...,
        description=(
            "Unreviewed reports about someone's safety. Its own number because "
            "it is the one reason where a place in the queue is the wrong answer."
        ),
    )
    stale_locks: int = Field(
        ...,
        description="Claimed, past the lock window, and never decided",
    )
    notices_30d: dict[str, int] = Field(..., description="warning · suspension · rename · picture")
    unacknowledged_notices: int


class HealthPanel(BaseModel):
    """What is quietly not working.

    Every field here is zero when the system is healthy, which is the point:
    a panel of activity numbers hides a stopped cron inside its noise, and the
    two purge jobs fail in a way that is invisible from outside — a deleted
    account past its window answers "not found" whether it was purged or not.
    """
    purge_overdue: int = Field(..., description="Accounts past their purge date; non-zero means the cron stopped")
    evidence_overdue: int = Field(..., description="Report evidence past retention and still stored")
    removed_content_overdue: int = Field(
        0,
        description="Posts and comments removed by moderation past REMOVED_CONTENT_RETENTION_DAYS and still stored"
    )
    error_occurrences_24h: int
    distinct_faults: int = Field(..., description="Rows in the error log — kinds of failure, not hits")
    last_host_access: Optional[datetime] = Field(None, description="Most recent SSH login to the machine")


class FlaggedAddress(BaseModel):
    """One client address producing an unusual number of refusals."""
    ip: str
    counts: dict[str, int] = Field(..., description="Refusals per kind inside the window")
    reasons: list[str] = Field(..., description="Which kinds passed their threshold")


class SecurityPanel(BaseModel):
    """Addresses worth a look — not addresses that were acted on.

    Nothing blocks on these numbers. The rate limiter already refuses on its
    own terms, and an automatic block driven by a failure count is a denial of
    service anyone can aim at a shared mobile NAT by pushing rubbish through it.
    """
    flagged_addresses: list[FlaggedAddress]
    window_seconds: int


class DayCount(BaseModel):
    date: str = Field(..., description="ISO day, not an instant")
    count: int


class SeriesPanel(BaseModel):
    """Daily history for the board's charts.

    Every day inside the window is present, zeros included. A series with its
    empty days removed is drawn as a line through the gaps, which turns three
    sign-ups in a month into a steady climb.
    """
    days: int = Field(..., description="The window these cover")
    periods: list[int] = Field(..., description="The windows the board offers")
    signups: list[DayCount]
    reports: list[DayCount]
    posts: list[DayCount] = Field(default_factory=list, description="Posts published per day — a count, never the posts")


class AdminOverviewResponse(BaseModel):
    accounts: AccountPanel
    moderation: ModerationPanel
    health: HealthPanel
    series: SeriesPanel
    security: SecurityPanel
    generated_at: datetime = Field(
        ...,
        description=(
            "When these numbers were computed. Cached for a short window, so a "
            "refresh can legitimately return the same instant — the panel says "
            "so rather than implying it just re-read the database."
        ),
    )


class AdminUserRow(BaseModel):
    """One account, as the admin list shows it.

    Deliberately no e-mail, no streak and nothing about recovery. The list is
    browsable, so everything on it is readable in bulk by anyone holding one
    admin credential — and this app was built so that who relapsed is not
    something a screen can enumerate.
    """
    id: str
    username: str
    status: int
    created_at: datetime
    banned_until: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    must_change_username: bool = False
    picture_blocked: bool = False

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class AdminErrorRow(BaseModel):
    """A distinct fault. One row is one *kind* of failure, however often it hit."""
    id: str
    kind: str
    exception_type: str
    method: str
    path: str
    status_code: int
    count: int
    last_seen: datetime
    created_at: datetime = Field(..., description="First seen")
    message: Optional[str] = None
    traceback: Optional[str] = None
    user_id: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class AdminHostAccessRow(BaseModel):
    occurred_at: datetime
    os_user: str
    source_ip: str
    method: str
    result: str

    model_config = ConfigDict(from_attributes=True, extra="forbid")
