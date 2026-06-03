from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.userBadgeService import UserBadgeService
from schemas.userBadgeSchemas import UserBadgeResponse, UserBadgeCreate, UserBadgeUpdate, UserBadgeListResponse
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from security.limiter import limiter
from typing import Union
from domain.entities.userBadge import UserBadge

import uuid


router = APIRouter(prefix="/user-badges", tags=["User Badges"])


@router.get("/{userBadgeId}",
            response_model=Union[PaginatedResponse[UserBadge], UserBadgeListResponse],
            summary="Get user badge by userId",
            description="Returns all user badges by userId.")
@limiter.limit("60/minute")
def getByUserId(
    userId: str,
    request: Request,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
    ):
    service = UserBadgeService(db)

    if paginated:
        userBadges = service.findByUserId(userId, paginatedParams)

        return userBadges
    else:
        userBadges = service.findByUserId(userId)
        assert isinstance(userBadges, list)
        return UserBadgeListResponse(
            badges=[UserBadgeResponse.model_validate(ub) for ub in userBadges],
            total=len(userBadges)
        )


@router.get("/{userBadgeId}",
            response_model=Union[PaginatedResponse[UserBadge], UserBadgeListResponse],
            summary="Get user badge by badgeId",
            description="Returns all user badges by badgeId.")
@limiter.limit("60/minute")
def getByBadgeId(
    badgeId: str,
    request: Request,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
    ):
    service = UserBadgeService(db)

    if paginated:
        userBadges = service.findByBadgeId(badgeId, paginatedParams)

        return userBadges
    else:
        userBadges = service.findByBadgeId(badgeId)
        assert isinstance(userBadges, list)
        return UserBadgeListResponse(
            badges=[UserBadgeResponse.model_validate(ub) for ub in userBadges],
            total=len(userBadges)
        )


@router.put("/update/{userBadgeId}",
            response_model=UserBadgeResponse,
            status_code=200,
            summary="Update a user badge",
            description="Updates an existing user badge.")
@limiter.limit("10/minute")
def updateUserBadge(
    userBadgeId: str,
    request: Request,
    body: UserBadgeUpdate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserBadgeService(db)

        userBadge = service.findById(userBadgeId)
        if body.given_at is not None:
            userBadge.given_at = body.given_at
        if body.status is not None:
            userBadge.status = body.status
        updated = service.update(userBadgeId, userBadge)
        return UserBadgeResponse.model_validate(updated)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/{userId}/{badgeId}",
             response_model=UserBadgeCreate,
             status_code=200,
             summary="Grant a user badge",
             description="Grants a badge to a user.")
@limiter.limit("10/minute")
def grantUserBadge(
    userId: str,
    badgeId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserBadgeService(db)
        grantedUserBadge = service.grant(userId, badgeId)  
        return grantedUserBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/revoke/{userId}/{badgeId}",
             response_model=UserBadgeResponse,
             status_code=200,
             summary="Revoke a user badge",
             description="Revokes a badge from a user.")
@limiter.limit("10/minute")
def revokeUserBadge(
    userId: str,
    badgeId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserBadgeService(db)
        revokedUserBadge = service.revoke(userId, badgeId)
        return revokedUserBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/update/{userBadgeId}/status/{status}",
             response_model=UserBadgeResponse,
             status_code=200,
             summary="Update a user badge status",
             description="Updates the status of an existing user badge.")
@limiter.limit("10/minute")
def updateUserBadgeStatus(
    status: str,
    userBadgeId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
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
@limiter.limit("10/minute")
def deleteUserBadge(
    userBadgeId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = UserBadgeService(db)
        deletedUserBadge = service.delete(userBadgeId)
        return deletedUserBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
