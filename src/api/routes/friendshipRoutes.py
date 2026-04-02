from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.friendshipService import FriendshipService
from schemas.friendshipSchemas import FriendshipResponse, FriendshipCreate, FriendshipUpdate, FriendshipListResponse
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from typing import Union, Literal
from domain.entities.friendship import Friendship
from core.config import config

import uuid

router = APIRouter(prefix="/friendships", tags=["Friendships"])


@router.get(
    "/{userId}",
    response_model=Union[PaginatedResponse[Friendship], FriendshipListResponse],
    summary="Get all friendships for current user",
    description="Returns all friendships where the current user is a sender or receiver."
)
def getFriendshipsByUserId(
    userId: str,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get all friendships for the current user.

    Returns:
        FriendshipListResponse: List of friendships
    """
    try:
        service = FriendshipService(db)
        
        if paginated:
            friendships = service.getByUserId(userId, paginatedParams)
            
            return friendships
        else:
            friendships = service.getByUserId(userId)
            
            return FriendshipListResponse(
                friendships=friendships,
                total=len(friendships)
            )
            
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.get(
    "/{userId}/pending",
    response_model=Union[PaginatedResponse[Friendship], FriendshipListResponse],
    summary="Get pending friendships by user ID",
    description="Returns all pending friendships by user ID."
)
def getPendingFriendshipsByUserId(
    userId: str,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get pending friendships by user ID.

    Args:
        userId: ID of the user
        paginated: If true, returns a paginated response
        paginatedParams: Pagination parameters

    Returns:
        Union[PaginatedResponse[Friendship], FriendshipListResponse]
    """
    try:
        service = FriendshipService(db)
        
        if paginated:
            friendships = service.getPendingReceived(userId, paginatedParams)
            
            return friendships
        else:
            friendships = service.getPendingReceived(userId)
            
            return FriendshipListResponse(
                friendships=friendships,
                total=len(friendships)
            )
            
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.get("/{userIdA}/{userIdB}",
            response_model=Union[PaginatedResponse[Friendship], FriendshipListResponse],
            summary="Get a friendship by user IDs",
            description="Returns a friendship by user IDs.")
def getFriendshipByUserIds(
    userIdA: str,
    userIdB: str,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get a friendship by user IDs.

    Args:
        userIdA: ID of the first user
        userIdB: ID of the second user
        paginated: If true, returns a paginated response
        paginatedParams: Pagination parameters

    Returns:
        Union[PaginatedResponse[Friendship], FriendshipListResponse]
    """
    try:
        service = FriendshipService(db)
        
        if paginated:
            friendships = service.getByUsers(userIdA, userIdB, paginatedParams)
            
            return friendships
        else:
            friendships = service.getByUsers(userIdA, userIdB)
            
            return FriendshipListResponse(
                friendships=friendships,
                total=len(friendships)
            )
            
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.get("/{friendshipId}",
            response_model=FriendshipResponse,
            summary="Get a friendship by ID",
            description="Returns a specific friendship by its ID.")
def getFriendshipById(
    friendshipId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get a specific friendship by ID.

    Args:
        friendshipId: UUID of the friendship

    Returns:
        FriendshipResponse: The friendship details
    """
    try:
        service = FriendshipService(db)
        friendship = service.get(friendshipId)
        
        return FriendshipResponse(
            id=friendship.id,
            sender=friendship.sender,
            reciver=friendship.reciver,
            status=friendship.status,
            createdAt=friendship.created_at,
            updatedAt=friendship.updated_at
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.put("/{friendshipId}",
            response_model=FriendshipResponse,
            status_code=200,
            summary="Update a friendship",
            description="Updates an existing friendship.")
def updateFriendship(
    friendshipId: str,
    request: FriendshipUpdate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update an existing friendship.

    Args:
        friendshipId: UUID of the friendship
        request: Friendship update data

    Returns:
        FriendshipResponse: The updated friendship
    """
    try:
        service = FriendshipService(db)
        
        # Update the friendship entity
        updatedFriendship = Friendship(
            id=friendshipId,
            sender=None,
            reciver=None,
            status=request.status,
            created_at=None,
            updated_at=None
        )

        updatedFriendship = service.update(friendshipId, updatedFriendship)
        return updatedFriendship
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.put("/{friendshipId}/status/{status}",
            response_model=FriendshipResponse,
            status_code=200,
            summary="Update a friendship status",
            description="Updates the status of an existing friendship.")
def updateFriendshipStatus(
    status: str,
    friendshipId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update the status of an existing friendship.

    Args:
        status: New status (ex: enabled, disabled)
        friendshipId: UUID of the friendship

    Returns:
        FriendshipResponse: The updated friendship
    """
    try:
        service = FriendshipService(db)

        updatedFriendship = service.updateStatus(friendshipId, status)
        return updatedFriendship
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.delete("/{friendshipId}",
            response_model=FriendshipResponse,
            status_code=200,
            summary="Delete a friendship",
            description="Soft deletes an existing friendship.")
def deleteFriendship(
    friendshipId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Delete an existing friendship.

    Args:
        friendshipId: UUID of the friendship

    Returns:
        FriendshipResponse: The deleted friendship
    """
    try:
        service = FriendshipService(db)
        deletedFriendship = service.delete(friendshipId)
        return deletedFriendship
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.post("/{userId}/accept",
             response_model=FriendshipResponse,
             status_code=200,
             summary="Accept a friendship request",
             description="Accepts a friendship request.")
def acceptFriendshipRequest(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Accept a friendship request.

    Args:
        userId: ID of the user

    Returns:
        FriendshipResponse: The accepted friendship
    """
    try:
        service = FriendshipService(db)
        
        # Accept the friendship request
        acceptedFriendship = service.accept(userId)
        return acceptedFriendship
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.post("/{userId}/reject",
             response_model=FriendshipResponse,
             status_code=200,
             summary="Reject a friendship request",
             description="Rejects a friendship request.")
def rejectFriendshipRequest(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Reject a friendship request.

    Args:
        userId: ID of the user

    Returns:
        FriendshipResponse: The rejected friendship
    """
    try:
        service = FriendshipService(db)
        
        # Reject the friendship request
        rejectedFriendship = service.reject(userId)
        return rejectedFriendship
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.post("/{userId}/block",
             response_model=FriendshipResponse,
             status_code=200,
             summary="Block a user",
             description="Blocks a user.")
def blockUser(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Block a user.

    Args:
        userId: ID of the user

    Returns:
        FriendshipResponse: The blocked user
    """
    try:
        service = FriendshipService(db)
        
        # Block the user
        blockedUser = service.block(userId)
        return blockedUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.post("/{userId}/unblock",
             response_model=FriendshipResponse,
             status_code=200,
             summary="Unblock a user",
             description="Unblocks a user.")
def unblockUser(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Unblock a user.

    Args:
        userId: ID of the user

    Returns:
        FriendshipResponse: The unblocked user
    """
    try:
        service = FriendshipService(db)
        
        # Unblock the user
        unblockedUser = service.unblock(userId)
        return unblockedUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.post("/{userId}",
             response_model=FriendshipCreate,
             status_code=200,
             summary="Send a friend request",
             description="Sends a friend request to a user.")
def sendFriendshipRequest(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Send a friend request.

    Args:
        userId: ID of the user

    Returns:
        FriendshipResponse: The sent friendship request
    """
    try:
        service = FriendshipService(db)
        
        newFriendship = Friendship(
            id=str(uuid.uuid4()),
            sender=str(currentUserId),
            reciver=str(userId),
            status=config.STATUS_CODES["pending"],
            created_at=None,
            updated_at=None
        )
        
        # Send the friend request
        sentFriendshipRequest = service.create(newFriendship)
        return sentFriendshipRequest
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.get("/exists/{userIdA}/{userIdB}",
            response_model=FriendshipResponse,
            summary="Check if a friendship exists",
            description="Checks if a friendship exists between two users.")
def checkFriendshipExists(
    userIdA: str,
    userIdB: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Check if a friendship exists.

    Args:
        userIdA: ID of the first user
        userIdB: ID of the second user

    Returns:
        FriendshipResponse: The sent friendship request
    """
    try:
        service = FriendshipService(db)
        
        # Check if the friendship exists
        exists = service.existsByUsers(userIdA, userIdB)
        return exists
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)