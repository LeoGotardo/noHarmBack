from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.userBadgeService import UserBadgeService
from schemas.userBadgeSchemas import UserBadgeResponse, UserBadgeCreate, UserBadgeUpdate, UserBadgeListResponse
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from typing import Union
from domain.entities.userBadge import UserBadge


import uuid

router = APIRouter(prefix="/user-badges", tags=["User Badges"])


@router.get("/{userBadgeId}",
            response_model=Union[PaginatedResponse[UserBadge], UserBadgeListResponse],
            summary="Get user badge by userId",
            description="Returns all user badges by userId.")
def getByUserId(
    userId: str,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
    ):
    """Get user badges by userId
    
    Args:
        userId (str): User ID
        paginated (bool, optional): If true, returns a paginated response. Defaults to False.
        paginatedParams (PaginationParams, optional): Pagination parameters. Defaults to Depends().
        
    Returns:
        UserBadgeListResponse: List of user badges
        
    """
    service = UserBadgeService(db)
    
    if paginated:
        userBadges = service.findByUserId(userId, paginatedParams)
        
        return userBadges
    else:
        userBadges = service.getByUserId(userId)
    
        return UserBadgeListResponse(
            userBadges=userBadges,
            total=len(userBadges)
        )


@router.get("/{userBadgeId}",
            response_model=Union[PaginatedResponse[UserBadge], UserBadgeListResponse],
            summary="Get user badge by badgeId",
            description="Returns all user badges by badgeId.")
def getByBadgeId(
    badgeId: str,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
    ):
    """Get user badges by badgeId
    
    Args:
        badgeId (str): Badge ID
        paginated (bool, optional): If true, returns a paginated response. Defaults to False.
        paginatedParams (PaginationParams, optional): Pagination parameters. Defaults to Depends().
        
    Returns:
        UserBadgeListResponse: List of user badges
        
    """
    service = UserBadgeService(db)
    
    if paginated:
        userBadges = service.findByBadgeId(badgeId, paginatedParams)
        
        return userBadges
    else:
        userBadges = service.getByBadgeId(badgeId)
    
        return UserBadgeListResponse(
            userBadges=userBadges,
            total=len(userBadges)
        )


@router.put("/update/{userBadgeId}",
            response_model=UserBadgeResponse,
            status_code=200,
            summary="Update a user badge",
            description="Updates an existing user badge.")
def updateUserBadge(
    userBadgeId: str,
    request: UserBadgeUpdate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update an existing user badge.    
    Args:
        userBadgeId: UUID of the user badge
        request: User badge update data
    Returns:
        UserBadgeResponse: The updated user badge
    """
    try:
        service = UserBadgeService(db)
        
        # Update the user badge entity
        updatedUserBadge = UserBadge(
            id=userBadgeId,
            user_id=request.user,
            badge_id=request.badge,
            given_at=request.givenAt,
            status=request.status
        )        
        updatedUserBadge = service.update(updatedUserBadge)
        return updatedUserBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/{userId}/{badgeId}",
             response_model=UserBadgeCreate,
             status_code=200,
             summary="Grant a user badge",
             description="Grants a badge to a user.")
def grantUserBadge(
    userId: str,
    badgeId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Grant a badge to a user.

    Args:
        userId: UUID of the user
        badgeId: UUID of the badge

    Returns:
        UserBadgeResponse: The granted user badge
    """
    try:
        service = UserBadgeService(db)
        
        # Grant the badge to the user
        grantedUserBadge = service.grant(userId, badgeId)
        return grantedUserBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/revoke/{userId}/{badgeId}",
             response_model=UserBadgeResponse,
             status_code=200,
             summary="Revoke a user badge",
             description="Revokes a badge from a user.")
def revokeUserBadge(
    userId: str,
    badgeId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Revoke a badge from a user.

    Args:
        userId: UUID of the user
        badgeId: UUID of the badge

    Returns:
        UserBadgeResponse: The revoked user badge
    """
    try:
        service = UserBadgeService(db)
        
        # Revoke the badge from the user
        revokedUserBadge = service.revoke(userId, badgeId)
        return revokedUserBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/update/{userBadgeId}/status/{status}",
             response_model=UserBadgeResponse,
             status_code=200,
             summary="Update a user badge status",
             description="Updates the status of an existing user badge.")
def updateUserBadgeStatus(
    status: str,
    userBadgeId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update the status of an existing user badge.

    Args:
        status: New status (ex: enabled, disabled)
        userBadgeId: UUID of the user badge

    Returns:
        UserBadgeResponse: The updated user badge
    """
    try:
        service = UserBadgeService(db)

        updatedUserBadge = service.updateStatus(userBadgeId, status)
        return updatedUserBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)



@router.delete("/{userBadgeId}",
            response_model=UserBadgeResponse,
            status_code=200,
            summary="Delete a user badge",
            description="Soft deletes an existing user badge.")
def deleteUserBadge(
    userBadgeId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Delete an existing user badge.

    Args:
        userBadgeId: UUID of the user badge

    Returns:
        UserBadgeResponse: The deleted user badge
    """
    try:
        service = UserBadgeService(db)
        deletedUserBadge = service.delete(userBadgeId)
        return deletedUserBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)