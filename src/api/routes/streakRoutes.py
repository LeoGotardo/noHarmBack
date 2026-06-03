from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from domain.services.streakService import StreakService
from schemas.streakSchemas import StreakResponse, StreakListResponse
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from security.limiter import limiter
from typing import Union
from domain.entities.streak import Streak


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
@limiter.limit("60/minute")
def getCurrentStreak(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        streak = service.getCurrentByUserId(currentUserId)
        return StreakResponse.model_validate(streak)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/record",
    response_model=StreakResponse,
    summary="Get my record streak",
    description="Returns the authenticated user's longest streak (isRecord = True)."
)
@limiter.limit("60/minute")
def getRecordStreak(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        streak = service.getRecordByUserId(currentUserId)
        return StreakResponse.model_validate(streak)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/history",
    response_model=Union[PaginatedResponse[Streak], StreakListResponse],
    summary="Get my streak history",
    description="Returns all past and current streaks for the authenticated user."
)
@limiter.limit("30/minute")
def getStreakHistory(
    request: Request,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        if paginated:
            return service.getAllByUserId(currentUserId, paginatedParams)
        streaks = service.getAllByUserId(currentUserId)
        assert isinstance(streaks, list)
        return StreakListResponse(
            streaks=[StreakResponse.model_validate(s) for s in streaks],
            total=len(streaks)
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
@limiter.limit("5/minute")
def startStreak(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        streak = service.startStreak(currentUserId)
        return StreakResponse.model_validate(streak)
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
@limiter.limit("5/minute")
def endStreak(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        newStreak = service.endStreak(currentUserId)
        return StreakResponse.model_validate(newStreak)
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
@limiter.limit("10/minute")
def checkin(
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = StreakService(db)
        streak = service.checkin(currentUserId)
        return StreakResponse.model_validate(streak)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
