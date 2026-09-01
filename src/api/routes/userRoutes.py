from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.userService import UserService
from schemas.userSchemas import UserResponse, UserListResponse, ProfileUpdateRequest, UserStatsResponse
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


@router.put(
    "/{userId}/status/{status}",
    response_model=UserResponse,
    status_code=200,
    summary="Update a user status (admin)",
    description="Updates the status of an existing user. Admin action — creates audit log type=5."
)
@limiter.limit("10/minute")
def updateUserStatus(
    status: int,
    userId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
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
