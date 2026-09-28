from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.dependencies.auth import getAdminUser
from api.dependencies.database import getDb
from domain.services.adminService import AdminService
from infrastructure.database.repositories.errorLogRepository import ErrorLogRepository
from infrastructure.database.repositories.hostAccessRepository import HostAccessRepository
from infrastructure.database.repositories.userRepository import UserRepository
from schemas.adminSchemas import (
    AdminErrorRow,
    AdminHostAccessRow,
    AdminOverviewResponse,
    AdminUserRow,
)
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from security.limiter import limiter

from typing import Optional
import redis

from core.config import config


router = APIRouter(prefix="/admin", tags=["Admin"])

# One client for the process, like the rate limiter's. The overview cache is the
# only thing that uses it, and a board that fails because Redis is down would be
# worse than a board that is a second slower.
try:
    _redis: Optional[redis.Redis] = redis.from_url(config.REDIS_URL, decode_responses=True)  # type: ignore[assignment]
except Exception:
    _redis = None


@router.get(
    "/overview",
    response_model=AdminOverviewResponse,
    summary="The admin board (admin)",
    description=(
        "Every number on the board in one response: accounts, moderation and "
        "what is quietly not working.\n\n"
        "**It aggregates and never enumerates.** There is no per-account "
        "streak, relapse or message count here. This app is built so that who "
        "is struggling cannot be read off a screen, and an admin panel is "
        "exactly the screen that would undo that by accident.\n\n"
        "The `health` block reads zero when nothing is wrong, which is its "
        "point: `purge_overdue` and `evidence_overdue` are the two retention "
        "jobs failing, and they fail invisibly — a deleted account past its "
        "window answers \"not found\" whether it was purged or not.\n\n"
        "`days` selects the window the daily series cover — one of 7, 30 or "
        "90; anything else falls back to 30. The cache is keyed by it, so "
        "switching the range cannot hand back the previous window's numbers "
        "under the new label.\n\n"
        "Cached for 60 seconds; `generated_at` says when the numbers were "
        "actually computed rather than implying the database was just read. "
        "Opening this writes audit type 16.\n\n"
        "Restricted to ADMIN_USER_IDS; any other caller gets a 404."
    ),
)
@limiter.limit("30/minute")
def getOverview(
    request: Request,
    # One of SERIES_PERIODS. Anything else silently falls back to the default:
    # this scopes a dashboard, and a 400 for `?days=45` would break the page
    # over a number nobody typed on purpose.
    days: Optional[int] = None,
    # `getDb`, no RLS context: tb_7, tb_11, tb_14 and tb_15 all have policies
    # that pass only without one, and tb_0's own policies are owner-scoped.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser),
):
    try:
        service = AdminService(db, redisClient=_redis)
        service.logBoardRead(currentUserId)
        return AdminOverviewResponse.model_validate(service.overview(days=days))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/users",
    response_model=PaginatedResponse[AdminUserRow],
    summary="Every account, including the hidden ones (admin)",
    description=(
        "The account directory as moderation needs to see it. `GET /users` "
        "hides deleted, banned and blocked accounts — which is right for the "
        "app and useless here, since those are the accounts an administrator "
        "is looking for.\n\n"
        "**No e-mail, no streak, nothing about recovery.** The list is "
        "browsable, so everything on it is readable in bulk by anyone holding "
        "one admin credential.\n\n"
        "Restricted to ADMIN_USER_IDS; any other caller gets a 404."
    ),
)
@limiter.limit("30/minute")
def listUsers(
    request: Request,
    status: Optional[int] = None,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser),
):
    try:
        repository = UserRepository(db)
        # The filter goes into the query, not onto the page: narrowing the page
        # afterwards answers "the banned accounts that happen to be on page
        # one" and reports the unfiltered total beside it.
        page = repository.findAll(paginatedParams, includeInactive=True, status=status)

        return PaginatedResponse[AdminUserRow](
            items=[AdminUserRow.model_validate(user) for user in page.items],
            total=page.total,
            page=page.page,
            pageSize=page.pageSize,
            totalPages=page.totalPages,
            hasNext=page.hasNext,
            hasPrevious=page.hasPrevious,
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/errors",
    response_model=PaginatedResponse[AdminErrorRow],
    summary="What is failing (admin)",
    description=(
        "The error log, most recently seen first. **One row is one kind of "
        "failure**, grouped by a fingerprint of the exception type, the route "
        "and the top of the traceback — `count` is how often it has hit. A "
        "crash loop is one row with a large number, not ten thousand rows.\n\n"
        "The message and the traceback are stored encrypted, because a "
        "SQLAlchemy traceback carries the statement's parameters: a failure in "
        "`messageService` puts a message body there and one in `userService` "
        "puts an e-mail address there.\n\n"
        "Restricted to ADMIN_USER_IDS; any other caller gets a 404."
    ),
)
@limiter.limit("30/minute")
def listErrors(
    request: Request,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser),
):
    try:
        page = ErrorLogRepository(db).findRecent(paginatedParams)
        return PaginatedResponse[AdminErrorRow](
            items=[AdminErrorRow.model_validate(row) for row in page.items],
            total=page.total,
            page=page.page,
            pageSize=page.pageSize,
            totalPages=page.totalPages,
            hasNext=page.hasNext,
            hasPrevious=page.hasPrevious,
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/access",
    response_model=PaginatedResponse[AdminHostAccessRow],
    summary="Who logged into the machine (admin)",
    description=(
        "SSH logins to the host, newest first, as its journal reported them. "
        "Written by a cron on the host piping into `ingest-host-access` — not "
        "by any request, and there is no endpoint that accepts one.\n\n"
        "Failed attempts are counted by the collector and deliberately not "
        "stored: a public SSH port collects thousands a day and they would "
        "bury the few logins this exists to show.\n\n"
        "**This is not proof.** Anyone with root on the box can edit the "
        "journal before the collector reads it. It catches access nobody "
        "expected, not an attacker covering their tracks.\n\n"
        "Restricted to ADMIN_USER_IDS; any other caller gets a 404."
    ),
)
@limiter.limit("30/minute")
def listHostAccess(
    request: Request,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser),
):
    try:
        page = HostAccessRepository(db).findRecent(paginatedParams)
        return PaginatedResponse[AdminHostAccessRow](
            items=[AdminHostAccessRow.model_validate(row) for row in page.items],
            total=page.total,
            page=page.page,
            pageSize=page.pageSize,
            totalPages=page.totalPages,
            hasNext=page.hasNext,
            hasPrevious=page.hasPrevious,
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
