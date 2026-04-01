from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.badgeService import BadgeService
from schemas.badgeSchemas import BadgeResponse, BadgeListResponse, BadgeCreate, BadgeUpdate
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from typing import Optional, Union, Literal
from domain.entities.badge import Badge
from core.config import config


import uuid

router = APIRouter(prefix="/badges", tags=["Badges"])


@router.get("",
            response_model=Union[PaginatedResponse[Badge], BadgeListResponse],
            summary="Get all badges for current user",
            description="Returns all badges for the current user.")
def getAllBadges(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser),
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
):
    """
    Get all badges for the current user.

    Returns:
        BadgeListResponse: List of badges with total count
    """
    try:
        service = BadgeService(db)
        
        if paginated:
            badges = service.getAllPaginated(paginatedParams)

            return badges
        else:
            badges = service.getAll()
            
            return BadgeListResponse(
                badges=badges,
                total=len(badges)
            )

    except NoHarmException as e:
        raise HTTPException(status_code=e.errorCode, detail=e.message)


@router.get("/{badgeId}",
            response_model=BadgeResponse,
            summary="Get a badge by ID",
            description="Returns a specific badge by its ID.")
def getBadgeById(
    badgeId: str,
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
        
        return BadgeResponse(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            milestone=badge.milestone,
            icon=badge.icon,
            status=badge.status
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put("/update/{badgeId}",
            response_model=BadgeResponse,
            status_code=200,
            summary="Update a badge",
            description="Updates an existing badge.")
def updateBadge(
    badgeId: str,
    request: BadgeUpdate,
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
        
        # Update the badge entity
        updatedBadge = Badge(
            id=badgeId,
            name=request.name,
            description=request.description,
            milestone=request.milestone,
            icon=request.icon,
            status=request.status
        )

        updatedBadge = service.update(updatedBadge)
        return updatedBadge
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/update/{badgeId}/status/{status}",
             response_model=BadgeResponse,
             status_code=200,
             summary="Update a badge status",
             description="Updates the status of an existing badge.")
def updateBadgeStatus(
    status: str,
    badgeId: str,
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
def createBadge(
    request: BadgeCreate,
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
            id=str(uuid.uuid4()),
            name=request.name,
            description=request.description,
            milestone=request.milestone,
            icon=request.icon,
            status=request.status
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
def deleteBadge(
    badgeId: str,
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