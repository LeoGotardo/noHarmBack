from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from domain.services.friendshipService import FriendshipService
from schemas.friendshipSchemas import FriendshipResponse, FriendshipListResponse
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from typing import Union
from domain.entities.friendship import Friendship


router = APIRouter(prefix="/friendships", tags=["Friendships"])


# ── list / search ─────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=Union[PaginatedResponse[Friendship], FriendshipListResponse],
    summary="Get my friendships",
    description="Returns all friendships for the authenticated user."
)
def getMyFriendships(
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        if paginated:
            return service.getAll(currentUserId, paginatedParams)
        friendships = service.getAll(currentUserId)
        return FriendshipListResponse(friendships=friendships, total=len(friendships))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/pending",
    response_model=Union[PaginatedResponse[Friendship], FriendshipListResponse],
    summary="Get pending friend requests (received)",
    description="Returns all pending friendship requests received by the authenticated user."
)
def getPendingReceived(
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        if paginated:
            return service.getPendingReceived(currentUserId, paginatedParams)
        friendships = service.getPendingReceived(currentUserId)
        return FriendshipListResponse(friendships=friendships, total=len(friendships))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/sent",
    response_model=Union[PaginatedResponse[Friendship], FriendshipListResponse],
    summary="Get pending friend requests (sent)",
    description="Returns all pending friendship requests sent by the authenticated user."
)
def getPendingSent(
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        if paginated:
            return service.getPendingSent(currentUserId, paginatedParams)
        friendships = service.getPendingSent(currentUserId)
        return FriendshipListResponse(friendships=friendships, total=len(friendships))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{friendshipId}",
    response_model=FriendshipResponse,
    summary="Get a friendship by ID",
    description="Returns a specific friendship. Only participants may access it."
)
def getFriendshipById(
    friendshipId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        friendship = service.get(friendshipId)
        return friendship
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── create ────────────────────────────────────────────────────────────────────

@router.post(
    "/{receiverId}",
    response_model=FriendshipResponse,
    status_code=201,
    summary="Send a friend request",
    description=(
        "Sends a friend request to the specified user (§3.1). "
        "Cannot send to yourself, cannot send if a non-deleted friendship already exists, "
        "and cannot send to a user who has blocked you."
    )
)
def sendFriendRequest(
    receiverId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        return service.sendRequest(currentUserId, receiverId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── respond ───────────────────────────────────────────────────────────────────

@router.post(
    "/{friendshipId}/accept",
    response_model=FriendshipResponse,
    status_code=200,
    summary="Accept a friend request",
    description=(
        "Accepts a pending friend request (§3.2). "
        "Only the recipient of the request can accept it."
    )
)
def acceptFriendRequest(
    friendshipId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        return service.accept(friendshipId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/{friendshipId}/reject",
    response_model=FriendshipResponse,
    status_code=200,
    summary="Reject a friend request",
    description=(
        "Rejects (ignores) a pending friend request (§3.2). "
        "Only the recipient of the request can reject it."
    )
)
def rejectFriendRequest(
    friendshipId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        return service.reject(friendshipId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── block / unblock ───────────────────────────────────────────────────────────

@router.post(
    "/{friendshipId}/block",
    response_model=FriendshipResponse,
    status_code=200,
    summary="Block a user",
    description=(
        "Blocks a user within a friendship (§3.3). "
        "Either participant may block the other at any time, regardless of current status."
    )
)
def blockUser(
    friendshipId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        return service.block(friendshipId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/{friendshipId}/unblock",
    response_model=FriendshipResponse,
    status_code=200,
    summary="Unblock a user",
    description="Unblocks a previously blocked user."
)
def unblockUser(
    friendshipId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        return service.unblock(friendshipId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── delete ────────────────────────────────────────────────────────────────────

@router.delete(
    "/{friendshipId}",
    status_code=200,
    summary="Remove a friendship",
    description="Soft-deletes the friendship. Only participants may remove it."
)
def deleteFriendship(
    friendshipId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = FriendshipService(db)
        return service.delete(friendshipId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
