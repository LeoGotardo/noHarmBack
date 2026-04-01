from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.badgeService import BadgeService
from schemas.badgeSchemas import BadgeResponse, BadgeListResponse
from exceptions.baseExceptions import NoHarmException

router = APIRouter(prefix="/badges", tags=["Badges"])


@router.get("/all")
def getAllBadges(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get all badges for the current user.

    Returns:
        BadgeListResponse: List of badges with total count
    """
    try:
        service = BadgeService(db)
        badges = service.getAll()

        return BadgeListResponse(
            badges=badges,
            total=len(badges)
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.errorCode, detail=e.message)