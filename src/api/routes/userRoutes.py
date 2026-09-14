from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.dependencies.auth import getAdminUser, getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.noticeService import NoticeService
from domain.services.userService import UserService
from schemas.noticeSchemas import NoticeResponse, WarnRequest
from schemas.userSchemas import (
    UserResponse,
    UserListResponse,
    ProfileUpdateRequest,
    UserStatsResponse,
    SuspendRequest,
    SuspensionResponse,
)
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from domain.entities.user import User
from security.limiter import limiter
from typing import Optional, Union



router = APIRouter(prefix="/users", tags=["Users"])


# ── /me ──────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get my profile",
    description="Returns the full private profile of the authenticated user."
)
@limiter.limit("60/minute")
def getMyProfile(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        user = service.getProfile(currentUserId)
        return UserResponse.model_validate(user)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update my profile",
    description=(
        "Updates allowed fields for the authenticated user. "
        "Only `username` and `profilePicture` can be changed here. "
        "Email changes require a separate verification flow. "
        "Status can never be changed via this endpoint."
    )
)
@limiter.limit("10/minute")
def updateMyProfile(
    request: Request,
    body: ProfileUpdateRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        user = service.updateProfile(currentUserId, body.username, body.profile_picture)
        return UserResponse.model_validate(user)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── public profile ────────────────────────────────────────────────────────────

@router.get(
    "/{userId}",
    response_model=UserResponse,
    summary="Get a user's public profile",
    description=(
        "Returns a user's public profile. "
        "Blocked users cannot view the profile of their blocker (§3.3)."
    )
)
@limiter.limit("60/minute")
def getPublicProfile(
    userId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        user = service.getPublicProfile(currentUserId, userId)
        return UserResponse.model_validate(user)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{userId}/stats",
    response_model=UserStatsResponse,
    summary="Get a user's public activity numbers",
    description=(
        "Active-streak days and badges held, for friends only. A non-friend "
        "gets `visible=false` with no numbers — the same answer a stranger's "
        "profile shows in the app. Blocked and deleted accounts 403/404 exactly "
        "as `GET /users/{userId}` does."
    )
)
@limiter.limit("60/minute")
def getPublicStats(
    userId: str,
    request: Request,
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getCurrentUser)
):
    # getDb, not getDbWithRLS: the streak and user-badge policies are owner-only,
    # so an RLS session scoped to the caller would read nothing for anyone else
    # and every friend would look like they had no activity. The friendship check
    # inside getPublicStats is what authorises the read.
    try:
        service = UserService(db)
        return UserStatsResponse(**service.getPublicStats(currentUserId, userId))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── admin / internal ──────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=Union[PaginatedResponse[User], UserListResponse],
    summary="Get all users",
    description=(
        "Returns the user directory. Pass `search` with a full username or email "
        "to look one person up — matches are exact, since both columns are "
        "encrypted and only their hashes are queryable (§5). "
        "Deleted, banned and blocked accounts are never listed."
    )
)
@limiter.limit("30/minute")
def getAllUsers(
    request: Request,
    search: Optional[str] = None,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)

        if paginated:
            if search:
                return service.search(search, paginatedParams)
            return service.findAll(paginatedParams)

        users = service.search(search) if search else service.findAll()
        return UserListResponse(users=[UserResponse.model_validate(u) for u in users], total=len(users))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/{userId}/warn",
    response_model=NoticeResponse,
    status_code=201,
    summary="Warn an account (admin)",
    description=(
        "Sends a warning. **Nothing about the account changes** — no ban, no "
        "limit — and that is the point: the rung between doing nothing and "
        "banning someone was missing, so every offence short of a ban got "
        "silence.\n\n"
        "The user sees it the next time they open the app and acknowledges it. "
        "It names the conduct, never the reporter: the promise that a reported "
        "user is never told who complained is what makes reports fileable.\n\n"
        "`self_harm` is refused here (400 `NOT_A_WARNING`). A report about "
        "someone's safety is usually a frightened friend, and answering it with "
        "a telling-off is the worst available move. Restricted to "
        "ADMIN_USER_IDS; any other caller gets a 404."
    )
)
@limiter.limit("20/minute")
def warnUser(
    userId: str,
    request: Request,
    body: WarnRequest,
    # `getDb`: tb_12's insert policy only passes for a session with no RLS
    # context, which is what keeps notices something only moderation writes.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = NoticeService(db)
        return service.warn(userId, body.reason, currentUserId, body.message)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{userId}/suspend",
    response_model=SuspensionResponse,
    status_code=200,
    summary="Suspend an account for a fixed time (admin)",
    description=(
        "Bans an account until a date — `days: null` bans it permanently. A "
        "suspension is the same `banned` status as a permanent ban plus an end "
        "date, and it lifts itself at the first sign-in afterwards; nothing has "
        "to run on a schedule.\n\n"
        "Separate from resolving a report on purpose: closing a complaint and "
        "punishing an account are two decisions, and a queue where one implies "
        "the other is a queue moderators stop reading. Restricted to "
        "ADMIN_USER_IDS; any other caller gets a 404.\n\n"
        "To end a suspension early, set the account back to enabled with "
        "`PUT /users/{id}/status/1` — that clears the date with it."
    )
)
@limiter.limit("10/minute")
def suspendUser(
    userId: str,
    request: Request,
    body: SuspendRequest,
    # `getDb` for the same reason as the status route below: the tb_0 UPDATE
    # policy is owner-only, so an admin acting on someone else under an RLS
    # context would match no row.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = UserService(db)
        suspended = service.suspend(userId, body.days, currentUserId)

        # Written beside the ban so the person is not guessing what happened
        # when they come back. Best effort: a suspension whose notice failed to
        # save is still a suspension, and failing here would leave the
        # moderator unsure which half landed.
        NoticeService(db).noticeOfSuspension(
            userId, body.reason or "other", currentUserId, body.message
        )

        return suspended
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{userId}/status/{status}",
    response_model=UserResponse,
    status_code=200,
    summary="Update a user status (admin)",
    description=(
        "Updates the status of an existing user. Admin action — creates audit log type=5. "
        "Restricted to the UIDs in ADMIN_USER_IDS; any other caller gets a 404. This is the "
        "route that bans, unbans and undeletes, so leaving it open to any signed-in user "
        "would let anyone lift their own ban."
    )
)
@limiter.limit("10/minute")
def updateUserStatus(
    status: int,
    userId: str,
    request: Request,
    # `getDb`, not `getDbWithRLS`: the RLS policy on tb_0 allows UPDATE only on
    # your own row, so an admin acting on someone else under an RLS context
    # would match no row and change nothing. Authorisation for this route is
    # `getAdminUser` — the allowlist — not the database policy.
    db: Session = Depends(getDb),
    currentUserId: str = Depends(getAdminUser)
):
    try:
        service = UserService(db)
        updatedUser = service.updateStatus(userId, status, requestingUserId=currentUserId)
        return updatedUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete(
    "/me",
    status_code=200,
    summary="Delete my account",
    description="Soft-deletes the authenticated user's own account (sets status = deleted). Only a user can delete their own account (§1.4)."
)
@limiter.limit("5/minute")
def deleteUser(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        return service.delete(currentUserId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
