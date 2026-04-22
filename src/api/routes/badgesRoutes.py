from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.badgeService import BadgeService
from schemas.badgeSchemas import BadgeResponse, BadgeListResponse, BadgeCreate, BadgeUpdate
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from typing import Optional, Union
from domain.entities.badge import Badge
from core.config import config

import uuid

router = APIRouter(prefix="/badges", tags=["Badges"])


@router.get(
    "",
    response_model=Union[PaginatedResponse[BadgeResponse], BadgeListResponse],
    summary="Get all badges for current user",
    description="Returns all badges for the current user."
)
def getAllBadges(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser),
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
):
    try:
        service = BadgeService(db)

        if paginated:
            result = service.getAll(paginatedParams)
            return PaginatedResponse(
                items=[BadgeResponse.model_validate(b) for b in result.items],
                total=result.total,
                page=result.page,
                pageSize=result.pageSize,
                totalPages=result.totalPages,
                hasNext=result.hasNext,
                hasPrevious=result.hasPrevious,
            )
        else:
            badges = service.getAll()
            return BadgeListResponse(
                badges=[BadgeResponse.model_validate(b) for b in badges],
                total=len(badges),
            )

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{badgeId}",
    response_model=BadgeResponse,
    summary="Get a badge by ID",
    description="Returns a specific badge by its ID."
)
def getBadgeById(
    badgeId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = BadgeService(db)
        badge = service.get(badgeId)
        return BadgeResponse.model_validate(badge)

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/update/{badgeId}",
    response_model=BadgeResponse,
    status_code=200,
    summary="Update a badge",
    description="Updates an existing badge."
)
def updateBadge(
    badgeId: str,
    request: BadgeUpdate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = BadgeService(db)

        updatedBadge = Badge(
            id=badgeId,
            name=request.name,
            description=request.description,
            milestone=request.milestone,
            icon=request.icon,
            status=request.status,
        )

        result = service.update(updatedBadge)
        return BadgeResponse.model_validate(result)

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/update/{badgeId}/status/{status}",
    status_code=200,
    summary="Update a badge status",
    description="Updates the status of an existing badge."
)
def updateBadgeStatus(
    status: str,
    badgeId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = BadgeService(db)
        service.updateStatus(badgeId, status)
        return {"status": "updated"}

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "",
    response_model=BadgeResponse,
    status_code=201,
    summary="Create a badge",
    description="Creates a new badge."
)
def createBadge(
    request: BadgeCreate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = BadgeService(db)

        newBadge = Badge(
            id=str(uuid.uuid4()),
            name=request.name,
            description=request.description,
            milestone=request.milestone,
            icon=request.icon,
            status=request.status,
        )

        createdBadge = service.create(newBadge)
        return BadgeResponse.model_validate(createdBadge)

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete(
    "/{badgeId}",
    status_code=200,
    summary="Delete a badge",
    description="Soft deletes an existing badge."
)
def deleteBadge(
    badgeId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = BadgeService(db)
        service.delete(badgeId)
        return {"status": "deleted"}

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
