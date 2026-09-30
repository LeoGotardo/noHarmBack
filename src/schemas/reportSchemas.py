from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime


# The reasons the app offers. A closed set rather than free text: moderation
# groups on it, and it is the only part of a report that is stored unencrypted.
# `self_harm` exists because this is a recovery app — a report about someone in
# danger is not the same queue as a report about spam, and the front end says so.
ReportReason = Literal[
    "harassment",
    "spam",
    "inappropriate",
    "impersonation",
    "self_harm",
    "other",
]


class ReportRequest(BaseModel):
    """What the app sends when someone files a report.

    `chatId` is an **id, never content**: the server copies the messages out of
    the database itself (`ReportService._captureChat`). A field carrying the
    quoted text would let a reporter write the other person's lines for them,
    which is the one thing evidence must not allow.
    """
    reason: ReportReason = Field(..., description="Why the user is being reported")
    details: Optional[str] = Field(None, max_length=1000, description="What happened, in the reporter's words")
    chatId: Optional[UUID] = Field(
        None,
        description="Conversation the report is about; its last messages are captured as evidence"
    )
    # Two more places a report can be filed from, both ids for the same reason
    # as `chatId`. Either one combines with `chatId` — the app sends the chat
    # whenever the two have one, and a post is no reason to drop it — but not
    # with each other (400 REPORT_TARGET_AMBIGUOUS).
    postId: Optional[UUID] = Field(None, description="Post the report is about; copied as evidence")
    commentId: Optional[UUID] = Field(
        None,
        description="Comment the report is about; copied as evidence together with the post it is under"
    )

    model_config = ConfigDict(extra="forbid")


class ReportResponse(BaseModel):
    id: UUID
    reporter: Optional[str] = Field(None, description="User ID who filed the report")
    # Nullable because the account can be purged while the report stands;
    # `reported_uid` is the copy that does not go away.
    reported: Optional[str] = Field(None, description="User ID the report is about")
    reported_uid: Optional[str] = Field(None, description="User ID as captured when the report was filed")
    reported_username: Optional[str] = Field(None, description="Username as captured when the report was filed")
    reason: str = Field(..., description="Report reason code")
    details: Optional[str] = Field(None, description="Free-text description")
    status: int = Field(..., description="4 open · 5 actioned · 6 dismissed")
    target_kind: Optional[str] = Field(None, description="Where it was filed from: chat · post · comment · null (a profile)")
    appended: bool = Field(
        False,
        description=(
            "True when this filing added its post or comment to your open report "
            "about the same person instead of opening a second one (answered 200, not 201)"
        )
    )
    created_at: datetime = Field(..., description="Created at")
    updated_at: datetime = Field(..., description="Updated at")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ReportListResponse(BaseModel):
    reports: list[ReportResponse]
    total: int


class ReporterStanding(BaseModel):
    """How this reporter's previous reports were decided.

    Context for a moderator, not a verdict. Someone whose reports are always
    dismissed is usually mistaken and occasionally malicious, and the queue
    cannot tell which — but a moderator who can see "nine filed, nine
    dismissed" reads the tenth differently, and that is the whole purpose.

    `weight` is `(accepted + 1) / (accepted + ignored + 2)`: the share of this
    reporter's decided reports that were actioned, smoothed so that a first-time
    reporter sits at 0.5 rather than at zero. Nobody is distrusted for having no
    history.
    """
    filed: int = Field(..., description="Reports this user has filed in total")
    accepted: int = Field(..., description="How many a moderator acted on")
    ignored: int = Field(..., description="How many a moderator dismissed")
    pending: int = Field(..., description="How many are still awaiting review")
    weight: float = Field(..., ge=0.0, le=1.0, description="Smoothed share of decided reports that were actioned")


class ModeratedReportResponse(ReportResponse):
    """A report as the moderation queue sees it — with who is reviewing it.

    Separate from `ReportResponse` because `GET /reports/mine` uses that one:
    telling a reporter which moderator is reading their report names a person
    to complain about, and answers a question they never asked. The same line
    keeps the three fields below out of it: a reporter must not learn how their
    own history is weighted, or how many other people have reported someone.
    """
    locked_by: Optional[str] = Field(None, description="Moderator currently reviewing it")
    locked_at: Optional[datetime] = Field(None, description="When they claimed it")

    reporter_username: Optional[str] = Field(
        None,
        description=(
            "Who filed it, by name. Admin-only, like everything else on this "
            "model: the promise that a reported user never learns who "
            "complained is about the reported user, not about the moderator "
            "deciding the case — who cannot weigh a complaint against an "
            "account they are looking at without knowing whether the same "
            "person filed the last four. Absent once the reporter is purged."
        )
    )

    reporter_standing: Optional[ReporterStanding] = Field(
        None,
        description="How this reporter's past reports were decided; absent once their account is purged"
    )
    open_against_reported: int = Field(
        0,
        description="Open reports naming the same user, this one included"
    )
    looks_coordinated: bool = Field(
        False,
        description=(
            "Open reports against this user have reached REPORT_BRIGADING_THRESHOLD. "
            "A prompt to check whether the reporters arrived together — never an "
            "action, since acting on a count is what a brigade is buying."
        )
    )


class ModeratedReportListResponse(BaseModel):
    reports: list[ModeratedReportResponse]
    total: int


class ReportEvidenceResponse(BaseModel):
    """One captured item behind a report — admin only.

    `content_hash` is the keyed blind index of `content`: recomputing it is how
    a reader checks the row was not edited after capture.
    """
    id: UUID
    report: UUID
    kind: str = Field(..., description="profile · message · post · comment · note")
    source_id: Optional[str] = Field(None, description="Id of the row this was copied from")
    author_id: Optional[str] = Field(None, description="Who wrote it")
    content: str = Field(..., description="The copy taken at filing time")
    content_hash: str = Field(..., description="Keyed hash of the content, for tamper detection")
    occurred_at: Optional[datetime] = Field(None, description="When the captured thing was said")
    created_at: datetime = Field(..., description="When it was captured")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ReportEvidenceListResponse(BaseModel):
    evidence: list[ReportEvidenceResponse]
    total: int
