from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from dataclasses import asdict
from typing import Literal, Optional, Union

from api.dependencies.auth import getCurrentUser, getAdminUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.entities.report import Report
from domain.services.reportService import ReportService
from schemas.reportSchemas import (
    ReportRequest,
    ReportResponse,
    ReportListResponse,
    ModeratedReportResponse,
    ModeratedReportListResponse,
    ReportEvidenceResponse,
    ReportEvidenceListResponse,
)
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from security.limiter import limiter


router = APIRouter(prefix="/reports", tags=["Reports"])


def _moderated(report: Report, signals: dict[str, dict]) -> ModeratedReportResponse:
    """A queue row: the report plus the two signals the row cannot carry itself.

    `asdict` rather than `model_validate(report)` because the signals have to be
    validated alongside the rest — building the model and then writing the
    fields onto it would skip that, and `reporter_standing` is a nested model.
    """
    return ModeratedReportResponse.model_validate({
        **asdict(report),
        **signals.get(str(report.id), {}),
    })


# ── file a report ─────────────────────────────────────────────────────────────

@router.post(
    "/{reportedUserId}",
    response_model=ReportResponse,
    status_code=201,
    summary="Report a user",
    description=(
        "Files a report about another user. The reported user is never notified, "
        "and the report changes nothing about the relationship — blocking is a "
        "separate action the reporter can also take. One open report per pair: "
        "reporting the same user again before a moderator reviewed the first is a 409.\n\n"
        "Pass `chatId` to attach the conversation: the server copies its last "
        "messages as evidence. The body carries the id only — never the text — so "
        "a report cannot quote words the other person did not write. Naming a chat "
        "you are not in is a 403; naming one the reported user is not in is a 400.\n\n"
        "**Per-account ceilings** (the rate limit above is per IP, which a single "
        "account reporting many different people never trips):\n"
        "- 403 `REPORTER_NOT_ELIGIBLE` — the reporter's own account is not enabled\n"
        "- 429 `REPORT_QUOTA_EXCEEDED` — past REPORT_MAX_PER_HOUR or REPORT_MAX_PER_DAY. "
        "Only reports that were actually filed count against it\n"
        "- 429 `TOO_MANY_OPEN_REPORTS` — REPORT_MAX_OPEN of this user's reports are "
        "already awaiting review; each one a moderator closes frees a slot\n"
        "- 409 `REPORT_RECENTLY_DISMISSED` — a moderator dismissed this reporter's "
        "last report about this same user less than REPORT_DISMISSED_COOLDOWN_DAYS ago. "
        "`details.canReportAgainAt` says when. A report that was *actioned* never "
        "cools down: repeat offending is the case you want to hear about at once"
    )
)
@limiter.limit("5/minute")
def reportUser(
    reportedUserId: str,
    request: Request,
    body: ReportRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    # NoHarmException is deliberately not converted to HTTPException here, for
    # the same reason as `/auth/register`: the handler in main.py serialises it
    # with `errorCode` and `details` intact, and the conversion keeps neither.
    # Four of the refusals below mean visibly different things to the app —
    # "verify your account", "you are filing too fast", "wait for the ones you
    # already filed", "we reviewed this and took no action" — and one of them
    # carries the date it lifts in `details.canReportAgainAt`. Flattened to
    # `detail=e.message`, every one of them arrives as a generic 4xx.
    service = ReportService(db)
    return service.report(currentUserId, reportedUserId, body.reason, body.details, body.chatId)


# ── my reports ────────────────────────────────────────────────────────────────

@router.get(
    "/mine",
    response_model=Union[PaginatedResponse[ReportResponse], ReportListResponse],
    summary="Get the reports I filed",
    description=(
        "Returns the authenticated user's own reports — what the app uses to show "
        "'already reported'. Nobody can read reports filed by someone else, and "
        "nobody can read reports filed about them."
    )
)
@limiter.limit("30/minute")
def getMyReports(
    request: Request,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ReportService(db)
        if paginated:
            return service.getMine(currentUserId, paginatedParams)
        reports = service.getMine(currentUserId)
        return ReportListResponse(reports=[ReportResponse.model_validate(r) for r in reports], total=len(reports))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── moderation queue (admin) ──────────────────────────────────────────────────

@router.get(
    "",
    response_model=Union[PaginatedResponse[ModeratedReportResponse], ModeratedReportListResponse],
    summary="Get the moderation queue (admin)",
    description=(
        "Returns every report, optionally filtered by status "
        "(4 open · 5 actioned · 6 dismissed). Restricted to the UIDs in "
        "ADMIN_USER_IDS; any other caller gets a 404.\n\n"
        "`locked_by` / `locked_at` say who is reviewing a report right now. A "
        "lock older than REPORT_LOCK_MINUTES (30) is stale and anyone may claim "
        "it — the queue should treat it as free.\n\n"
        "`sort=priority` puts self-harm reports first — whoever filed them — then "
        "orders by `reporter_standing.weight`. Nothing is hidden: a report from "
        "someone whose complaints are always dismissed still sits in the queue, "
        "just not ahead of everyone else's.\n\n"
        "`reporter_standing` is how that reporter's past reports were decided, and "
        "`open_against_reported` how many open reports name the same account. "
        "`looks_coordinated` marks the second passing REPORT_BRIGADING_THRESHOLD — a "
        "prompt to check whether the reporters arrived together, never an action."
    )
)
@limiter.limit("30/minute")
def getReports(
    request: Request,
    status: Optional[int] = None,
    sort: Literal["newest", "priority"] = Query(
        "newest",
        description="newest = chronological · priority = self-harm first, then by reporter standing"
    ),
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    # `getDb`, not `getDbWithRLS`: tb_10's select policy is reporter-only, so a
    # moderator reading someone else's report under an RLS context would match
    # no rows. Authorisation here is `getAdminUser` — the allowlist.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = ReportService(db)

        if paginated:
            page = service.getAll(status, paginatedParams, sort)
            signals = service.signalsFor(page.items)
            return page.model_copy(update={
                "items": [_moderated(r, signals) for r in page.items]
            })

        reports = service.getAll(status, None, sort)
        signals = service.signalsFor(reports)
        return ModeratedReportListResponse(
            reports=[_moderated(r, signals) for r in reports],
            total=len(reports)
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{reportId}",
    response_model=ReportResponse,
    summary="Get a report by ID (admin)",
    description="Returns a single report. Restricted to ADMIN_USER_IDS."
)
@limiter.limit("30/minute")
def getReportById(
    reportId: str,
    request: Request,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = ReportService(db)
        return service.get(reportId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{reportId}/evidence",
    response_model=ReportEvidenceListResponse,
    summary="Read the evidence behind a report (admin)",
    description=(
        "Returns what was captured when the report was filed — the reported "
        "profile as it was, and the tail of the conversation when one was named. "
        "Restricted to ADMIN_USER_IDS; any other caller gets a 404.\n\n"
        "Every call writes an audit entry (type 11). This is private "
        "correspondence between two users, and a power to read it that leaves no "
        "trace is indistinguishable from one being abused."
    )
)
@limiter.limit("30/minute")
def getReportEvidence(
    reportId: str,
    request: Request,
    # `getDb` for the same reason as the queue: tb_11 is readable only by a
    # session with no RLS context.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = ReportService(db)
        evidence = service.getEvidence(reportId, currentUserId)
        return ReportEvidenceListResponse(
            evidence=[ReportEvidenceResponse.model_validate(item) for item in evidence],
            total=len(evidence)
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/{reportId}/claim",
    response_model=ModeratedReportResponse,
    summary="Take a report for review (admin)",
    description=(
        "Marks a report as being reviewed by the caller, so a second moderator "
        "does not read the same conversation and act on it twice. 409 when "
        "someone else holds it, 400 once it has been reviewed.\n\n"
        "The claim expires after REPORT_LOCK_MINUTES (30), so a moderator who "
        "closes the tab cannot park a report for ever. Claiming again before "
        "then restarts the clock. Claiming is not required to resolve — it "
        "matters only where there is more than one moderator."
    )
)
@limiter.limit("30/minute")
def claimReport(
    reportId: str,
    request: Request,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = ReportService(db)
        return service.claim(reportId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete(
    "/{reportId}/claim",
    response_model=ModeratedReportResponse,
    summary="Put a report back in the queue (admin)",
    description=(
        "Releases the review lock without deciding anything. Only the holder "
        "can release it — or anyone once the lock has expired, since by then "
        "nobody holds it."
    )
)
@limiter.limit("30/minute")
def releaseReport(
    reportId: str,
    request: Request,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = ReportService(db)
        return service.release(reportId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{reportId}/resolve/{status}",
    response_model=ReportResponse,
    summary="Resolve a report (admin)",
    description=(
        "Closes an open report: `accepted` when a moderator acted on it, `ignored` "
        "when they dismissed it. 409 when another moderator holds the review "
        "lock.\n\n"
        "Acting on the account stays a separate call — PUT /users/{id}/suspend "
        "for a timed suspension or a permanent ban, PUT /users/{id}/status/{status} "
        "to lift one. Resolving never changes an account on its own: closing a "
        "complaint and punishing someone are two decisions."
    )
)
@limiter.limit("20/minute")
def resolveReport(
    reportId: str,
    status: str,
    request: Request,
    # No RLS context for the same reason as the queue above, and because tb_10
    # grants UPDATE only to a session without one: a reporter cannot rewrite
    # their own report.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = ReportService(db)
        return service.resolve(reportId, status, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
