from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, model_validator
from typing import Optional

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from domain.services.messageService import MessageService
from schemas.messageSchemas import MessageResponse, MessageListResponse
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from security.limiter import limiter
from typing import Union
from uuid import UUID

router = APIRouter(prefix="/messages", tags=["Messages"])


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    chatId: Optional[UUID] = Field(None, description="Existing chat to send to")
    recipientId: Optional[str] = Field(None, description="Recipient user ID — the chat is created if none exists yet")

    @model_validator(mode="after")
    def _exactly_one_target(self):
        if bool(self.chatId) == bool(self.recipientId):
            raise ValueError("Provide exactly one of 'chatId' or 'recipientId'.")
        return self


# ── list ──────────────────────────────────────────────────────────────────────

@router.get(
    "/chat/{chatId}",
    response_model=Union[PaginatedResponse[MessageResponse], MessageListResponse],
    summary="Get messages in a chat",
    description="Returns all messages for a chat. Only participants may access them (§5.2, RLS)."
)
@limiter.limit("60/minute")
def getMessagesByChatId(
    chatId: UUID,
    request: Request,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        if paginated:
            return service.getByChatId(chatId, paginatedParams)
        messages = service.getByChatId(chatId)
        return MessageListResponse(messages=[MessageResponse.model_validate(m) for m in messages], total=len(messages))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/chat/{chatId}/unread",
    response_model=Union[PaginatedResponse[MessageResponse], MessageListResponse],
    summary="Get unread messages in a chat",
    description="Returns all unread messages in the given chat."
)
@limiter.limit("60/minute")
def getUnreadMessagesByChatId(
    chatId: UUID,
    request: Request,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        if paginated:
            return service.getUnreadByChatId(chatId, paginatedParams)
        messages = service.getUnreadByChatId(chatId)
        return MessageListResponse(messages=[MessageResponse.model_validate(m) for m in messages], total=len(messages))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{messageId}",
    response_model=MessageResponse,
    summary="Get a message by ID",
    description="Returns a specific message."
)
@limiter.limit("60/minute")
def getMessageById(
    messageId: UUID,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        return service.get(messageId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── send ──────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=MessageResponse,
    status_code=201,
    summary="Send a message",
    description=(
        "Sends a message to a chat (§5.1). "
        "The chat must be active (enabled or pending — pending chats auto-activate on first message). "
        "Content is sanitised; empty content after sanitisation is rejected. "
        "status = unread, sendAt = now."
    )
)
@limiter.limit("30/minute")
def sendMessage(
    request: Request,
    body: SendMessageRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        if body.chatId is not None:
            return service.sendMessage(body.chatId, currentUserId, body.content)
        if body.recipientId is None:
            # _exactly_one_target already rejects this, so it is unreachable in
            # practice. Kept as a real check rather than an assert: `python -O`
            # strips asserts, and a silent None here would surface as a
            # TypeError deep in the service instead of a 400 at the edge.
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_DATA",
                message="Provide exactly one of 'chatId' or 'recipientId'."
            )
        return service.sendMessageToUser(currentUserId, body.recipientId, body.content)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── read receipts ─────────────────────────────────────────────────────────────

@router.put(
    "/{messageId}/read",
    response_model=MessageResponse,
    status_code=200,
    summary="Mark a message as read",
    description="Marks a specific message as read (§5.3). Idempotent — already-read messages are not updated."
)
@limiter.limit("60/minute")
def markMessageAsRead(
    messageId: UUID,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        return service.markAsRead(messageId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/chat/{chatId}/read",
    status_code=200,
    summary="Mark all messages as read",
    description="Marks all unread messages in a chat as read (§5.3)."
)
@limiter.limit("30/minute")
def markAllMessagesAsRead(
    chatId: UUID,
    request: Request,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        return service.markAllAsRead(chatId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
