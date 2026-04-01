from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.streakService import StreakService
from schemas.streakSchemas import StreakResponse, StreakCreate, StreakUpdate, StreakListResponse
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from typing import Optional, Union, Literal
from domain.entities.streak import Streak
from datetime import datetime

import uuid


router = APIRouter(prefix="/streaks", tags=["Streaks"])


@router.get("/{streakId}",
            response_model=StreakResponse,
            summary="Get a streak by ID",
            description="Returns a specific streak by its ID.")
def getStreakById(
    streakId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get a specific streak by ID.

    Args:
        streakId: UUID of the streak

    Returns:
        StreakResponse: The streak details
    """
    try:
        service = StreakService(db)
        streak = service.get(streakId)
        
        return StreakResponse(
            id=streak.id,
            owner=streak.owner_id,
            start=streak.start,
            end=streak.end,
            status=streak.status,
            isRecord=streak.is_record,
            createdAt=streak.created_at
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get("/current/{userId}",
            response_model=StreakResponse,
            summary="Get current streak by user ID",
            description="Returns the current streak by user ID.")
def getCurrentStreak(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get the current streak by user ID.

    Args:
        userId: UUID of the user

    Returns:
        StreakResponse: The current streak
    """
    try:
        service = StreakService(db)
        streak = service.getCurrentByUserId(userId)
        
        return StreakResponse(
            id=streak.id,
            owner=streak.owner_id,
            start=streak.start,
            end=streak.end,
            status=streak.status,
            isRecord=streak.is_record,
            createdAt=streak.created_at
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get("/record/{userId}",
            response_model=StreakResponse,
            summary="Get record streak by user ID",
            description="Returns the record streak by user ID.")
def getRecordStreak(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get the record streak by user ID.

    Args:
        userId: UUID of the user

    Returns:
        StreakResponse: The record streak
    """
    try:
        service = StreakService(db)
        streak = service.getRecordByUserId(userId)
        
        return StreakResponse(
            id=streak.id,
            owner=streak.owner_id,
            start=streak.start,
            end=streak.end,
            status=streak.status,
            isRecord=streak.is_record,
            createdAt=streak.created_at
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get("/history/{userId}",
            response_model=Union[PaginatedResponse[Streak], StreakListResponse],
            summary="Get streak history by user ID",
            description="Returns all streaks by user ID.")
def getStreakHistory(
    userId: str,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get streak history by user ID.

    Args:
        userId: UUID of the user
        paginated: If true, returns a paginated response
        paginatedParams: Pagination parameters

    Returns:
        Union[PaginatedResponse[Streak], StreakListResponse]: List of streaks
    """
    try:
        service = StreakService(db)
        
        if paginated:
            streaks = service.getAllByUserIdPaginated(userId, paginatedParams)
            
            return streaks
        else:
            streaks = service.getAllByUserId(userId)
            
            return StreakListResponse(
                streaks=streaks,
                total=len(streaks)
            )
            
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/update/{streakId}",
            response_model=StreakResponse,
            status_code=200,
            summary="Update a streak",
            description="Updates an existing streak.")
def updateStreak(
    streakId: str,
    request: StreakUpdate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update an existing streak.

    Args:
        streakId: UUID of the streak
        request: Streak update data

    Returns:
        StreakResponse: The updated streak
    """
    try:
        service = StreakService(db)
        
        # Update the streak entity
        updatedStreak = Streak(
            id=streakId,
            owner_id=request.owner,
            start=request.start,
            end=request.end,
            status=request.status,
            is_record=request.isRecord
        )

        updatedStreak = service.update(updatedStreak)
        return updatedStreak
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/update/{streakId}/status/{status}",
             response_model=StreakResponse,
             status_code=200,
             summary="Update a streak status",
             description="Updates the status of an existing streak.")
def updateStreakStatus(
    status: str,
    streakId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update the status of an existing streak.

    Args:
        status: New status (ex: enabled, disabled)
        streakId: UUID of the streak

    Returns:
        StreakResponse: The updated streak
    """
    try:
        service = StreakService(db)

        updatedStreak = service.updateStatus(streakId, status)
        return updatedStreak
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("",
            response_model=StreakResponse,
            status_code=201,
            summary="Create a streak",
            description="Creates a new streak.")
def createStreak(
    request: StreakCreate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Create a new streak.

    Args:
        request: Streak creation data

    Returns:
        StreakResponse: The created streak
    """
    try:
        service = StreakService(db)

        # Create the streak entity
        newStreak = Streak(
            id=str(uuid.uuid4()),
            owner_id=request.owner,
            start=request.start,
            end=request.end,
            status=request.status,
            is_record=request.isRecord
        )

        createdStreak = service.create(newStreak)
        return createdStreak
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("/end/{streakId}",
             response_model=StreakResponse,
             status_code=200,
             summary="End a streak",
             description="Sets the end of an existing streak.")
def endStreak(
    streakId: str,
    endedAt: datetime,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    End an existing streak.

    Args:
        streakId: UUID of the streak

    Returns:
        StreakResponse: The updated streak
    """
    try:
        service = StreakService(db)
        updatedStreak = service.updateEndedAt(streakId, endedAt)
        return updatedStreak
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("{streakId}/record",
             response_model=StreakResponse,
             status_code=200,
             summary="Mark a streak as record",
             description="Marks an existing streak as record.")
def markAsRecord(
    streakId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Mark an existing streak as record.

    Args:
        streakId: UUID of the streak

    Returns:
        StreakResponse: The updated streak
    """
    try:
        service = StreakService(db)
        updatedStreak = service.markAsRecord(streakId)
        return updatedStreak
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete("/{streakId}",
            response_model=StreakResponse,
            status_code=200,
            summary="Delete a streak",
            description="Soft deletes an existing streak.")
def deleteStreak(
    streakId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Delete an existing streak.

    Args:
        streakId: UUID of the streak

    Returns:
        StreakResponse: The deleted streak
    """
    try:
        service = StreakService(db)
        deletedStreak = service.delete(streakId)
        return deletedStreak
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)