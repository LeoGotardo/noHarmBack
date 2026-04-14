from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.userService import UserService
from schemas.userSchemas import UserCreate, UserUpdate, UserResponse, UserListResponse
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from domain.entities.user import User
from typing import Union

import uuid


router = APIRouter(prefix="/users", tags=["Users"])


class ProfileUpdateRequest(BaseModel):
    username: Optional[str] = None
    profilePicture: Optional[bytes] = None


# ── /me ──────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get my profile",
    description="Returns the full private profile of the authenticated user."
)
def getMyProfile(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        user = service.getProfile(currentUserId)
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
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
def updateMyProfile(
    request: ProfileUpdateRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        user = service.updateProfile(currentUserId, request.username, request.profilePicture)
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
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
def getPublicProfile(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        user = service.getPublicProfile(currentUserId, userId)
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── admin / internal ──────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=Union[PaginatedResponse[User], UserListResponse],
    summary="Get all users",
    description="Returns all users (admin use)."
)
def getAllUsers(
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        if paginated:
            return service.findAll(paginatedParams)
        users = service.findAll()
        return UserListResponse(users=users, total=len(users))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{userId}/status/{status}",
    response_model=UserResponse,
    status_code=200,
    summary="Update a user status (admin)",
    description="Updates the status of an existing user. Admin action — creates audit log type=5."
)
def updateUserStatus(
    status: int,
    userId: str,
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
def deleteUser(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserService(db)
        return service.delete(currentUserId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
