from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.badgeService import BadgeService
from schemas.badgeSchemas import BadgeResponse, BadgeListResponse, BadgeCreate, BadgeUpdate
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from security.limiter import limiter
from typing import Optional, Union, Literal
from domain.entities.badge import Badge
from core.config import config


import uuid

router = APIRouter(prefix="/badges", tags=["Badges"])


@router.get("",
            response_model=Union[PaginatedResponse[Badge], BadgeListResponse],
            summary="Get all badges",
            description="Returns all badges.")
@limiter.limit("60/minute")
def getAllBadges(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser),
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
):
    """
    Get all badges.

    Returns:
        BadgeListResponse: List of badges with total count
    """
    try:
        service = BadgeService(db)
        
        if paginated:
            badges = service.getAll(paginatedParams)

            return badges
        else:
            badges = service.getAll()
            
            assert isinstance(badges, list)
            return BadgeListResponse(
                badges=[BadgeResponse.model_validate(b) for b in badges],
                total=len(badges)
            )

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)  


@router.get("/{badgeId}",
            response_model=BadgeResponse,
            summary="Get a badge by ID",
            description="Returns a specific badge by its ID.")
@limiter.limit("60/minute")
def getBadgeById(
    badgeId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get a specific badge by ID.

    Args:
        badgeId: UUID of the badge

    Returns:
        BadgeResponse: The badge details
    """
    try:
        service = BadgeService(db)
        badge = service.get(badgeId)
        
        return BadgeResponse.model_validate(badge)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put("/update/{badgeId}",
            response_model=BadgeResponse,
            status_code=200,
            summary="Update a badge",
            description="Updates an existing badge.")
@limiter.limit("10/minute")
def updateBadge(
    badgeId: str,
    request: Request,
    body: BadgeUpdate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update an existing badge.

    Args:
        badgeId: UUID of the badge
        request: Badge update data

    Returns:
        BadgeResponse: The updated badge
    """
    try:
        service = BadgeService(db)
        badge = service.get(badgeId)
        if body.name is not None:
            badge.name = body.name
        if body.description is not None:
            badge.description = body.description
        if body.milestone is not None:
            badge.milestone = body.milestone
        if body.icon is not None:
            badge.icon = body.icon
        if body.status is not None:
            badge.status = body.status
        updated = service.update(badgeId, badge)
        return BadgeResponse.model_validate(updated)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/update/{badgeId}/status/{status}",
             response_model=BadgeResponse,
             status_code=200,
             summary="Update a badge status",
             description="Updates the status of an existing badge.")
@limiter.limit("10/minute")
def updateBadgeStatus(
    status: str,
    badgeId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update the status of an existing badge.

    Args:
        status: New status (ex: enabled, disabled)
        badgeId: UUID of the badge

    Returns:
        BadgeResponse: The updated badge
    """
    try:
        service = BadgeService(db)

        updatedBadge = service.updateStatus(badgeId, status)  
        return updatedBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("",
            response_model=BadgeResponse,
            status_code=201,
            summary="Create a badge",
            description="Creates a new badge.")
@limiter.limit("10/minute")
def createBadge(
    request: Request,
    body: BadgeCreate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Create a new badge.

    Args:
        request: Badge creation data

    Returns:
        BadgeResponse: The created badge
    """
    try:
        service = BadgeService(db)

        # Create the badge entity
        newBadge = Badge(
            name=body.name,
            description=body.description,
            milestone=body.milestone,
            icon=body.icon,
            status=body.status,
            created_at=body.created_at,
            updated_at=body.updated_at
        )

        createdBadge = service.create(newBadge)
        return createdBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete("/{badgeId}",
            response_model=BadgeResponse,
            status_code=200,
            summary="Delete a badge",
            description="Soft deletes an existing badge.")
@limiter.limit("10/minute")
def deleteBadge(
    badgeId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Delete an existing badge.

    Args:
        badgeId: UUID of the badge

    Returns:
        BadgeResponse: The deleted badge
    """
    try:
        service = BadgeService(db)
        deletedBadge = service.delete(badgeId)
        return deletedBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)