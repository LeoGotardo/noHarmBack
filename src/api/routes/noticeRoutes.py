from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from domain.services.noticeService import NoticeService
from schemas.noticeSchemas import NoticeResponse, NoticeListResponse
from exceptions.baseExceptions import NoHarmException
from security.limiter import limiter


router = APIRouter(prefix="/notices", tags=["Moderation notices"])


@router.get(
    "/mine",
    response_model=NoticeListResponse,
    summary="What moderation has told me",
    description=(
        "The warnings and suspension notices on this account, oldest first. "
        "Pass `pending=true` for only the ones not yet acknowledged — what the "
        "app shows on open.\\n\\n"
        "A notice never names who reported the user: it names the conduct. That "
        "promise is what makes reporting usable at all."
    )
)
@limiter.limit("30/minute")
def getMyNotices(
    request: Request,
    pending: bool = False,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = NoticeService(db)
        notices = service.getMine(currentUserId, unacknowledgedOnly=pending)
        return NoticeListResponse(
            notices=[NoticeResponse.model_validate(n) for n in notices],
            total=len(notices)
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/{noticeId}/ack",
    response_model=NoticeResponse,
    summary="Acknowledge a notice",
    description=(
        "Marks a notice as read, so it stops being shown. Only its recipient "
        "can: anyone else gets a 404. Acknowledging is not agreeing — the "
        "appeal route is a message to support, and the notice stays on file "
        "either way."
    )
)
@limiter.limit("30/minute")
def acknowledgeNotice(
    noticeId: str,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = NoticeService(db)
        return service.acknowledge(noticeId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
