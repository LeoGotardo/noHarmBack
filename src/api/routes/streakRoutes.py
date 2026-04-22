from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from domain.services.streakService import StreakService
from schemas.streakSchemas import StreakResponse, StreakListResponse
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from typing import Union
router = APIRouter(prefix="/streaks", tags=["Streaks"])


@router.get(
    "/current",
    response_model=StreakResponse,
    summary="Get my current streak",
    description=(
        "Returns the authenticated user's active streak. "
        "Auto-expires and resets the streak if no activity was recorded in the last 24 h (§6.3)."
    )
)
def getCurrentStreak(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        streak = service.getCurrentByUserId(currentUserId)
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


@router.get(
    "/record",
    response_model=StreakResponse,
    summary="Get my record streak",
    description="Returns the authenticated user's longest streak (isRecord = True)."
)
def getRecordStreak(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        streak = service.getRecordByUserId(currentUserId)
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


@router.get(
    "/history",
    response_model=Union[PaginatedResponse[StreakResponse], StreakListResponse],
    summary="Get my streak history",
    description="Returns all past and current streaks for the authenticated user."
)
def getStreakHistory(
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        if paginated:
            result = service.getAllByUserId(currentUserId, paginatedParams)
            return PaginatedResponse(
                items=[StreakResponse(id=s.id, owner=s.owner_id, start=s.start, end=s.end, status=s.status, isRecord=s.is_record, createdAt=s.created_at) for s in result.items],
                total=result.total,
                page=result.page,
                pageSize=result.pageSize,
                totalPages=result.totalPages,
                hasNext=result.hasNext,
                hasPrevious=result.hasPrevious,
            )
        streaks = service.getAllByUserId(currentUserId)
        return StreakListResponse(
            streaks=[StreakResponse(id=s.id, owner=s.owner_id, start=s.start, end=s.end, status=s.status, isRecord=s.is_record, createdAt=s.created_at) for s in streaks],
            total=len(streaks),
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/start",
    response_model=StreakResponse,
    status_code=201,
    summary="Start a new streak",
    description=(
        "Creates a new active streak. "
        "Fails with 409 if an active streak already exists (§6.1). "
        "start = now, isRecord = False."
    )
)
def startStreak(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        streak = service.startStreak(currentUserId)
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


@router.post(
    "/end",
    response_model=StreakResponse,
    status_code=200,
    summary="End (reset) my streak",
    description=(
        "Manually ends the active streak, checks whether it is a new personal record, "
        "and immediately starts a fresh streak (§6.2). "
        "Creates an audit log entry of type 7."
    )
)
def endStreak(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        newStreak = service.endStreak(currentUserId)
        return StreakResponse(
            id=newStreak.id,
            owner=newStreak.owner_id,
            start=newStreak.start,
            end=newStreak.end,
            status=newStreak.status,
            isRecord=newStreak.is_record,
            createdAt=newStreak.created_at
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/checkin",
    response_model=StreakResponse,
    status_code=200,
    summary="Daily check-in",
    description=(
        "Confirms the user's sobriety for today, refreshing the streak's activity timestamp. "
        "Must be called at least once every 24 h to prevent auto-expiry (§6.3)."
    )
)
def checkin(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        streak = service.checkin(currentUserId)
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
