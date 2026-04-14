from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from domain.services.messageService import MessageService
from schemas.messageSchemas import MessageResponse, MessageListResponse
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from typing import Union

router = APIRouter(prefix="/messages", tags=["Messages"])


class SendMessageRequest(BaseModel):
    chatId: str
    content: str = Field(..., min_length=1, max_length=2000)


# ── list ──────────────────────────────────────────────────────────────────────

@router.get(
    "/chat/{chatId}",
    response_model=Union[PaginatedResponse[MessageResponse], MessageListResponse],
    summary="Get messages in a chat",
    description="Returns all messages for a chat. Only participants may access them (§5.2, RLS)."
)
def getMessagesByChatId(
    chatId: str,
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
        return MessageListResponse(messages=messages, total=len(messages))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/chat/{chatId}/unread",
    response_model=Union[PaginatedResponse[MessageResponse], MessageListResponse],
    summary="Get unread messages in a chat",
    description="Returns all unread messages in the given chat."
)
def getUnreadMessagesByChatId(
    chatId: str,
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
        return MessageListResponse(messages=messages, total=len(messages))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{messageId}",
    response_model=MessageResponse,
    summary="Get a message by ID",
    description="Returns a specific message."
)
def getMessageById(
    messageId: str,
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
def sendMessage(
    request: SendMessageRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        return service.sendMessage(request.chatId, currentUserId, request.content)
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
def markMessageAsRead(
    messageId: str,
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
def markAllMessagesAsRead(
    chatId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        return service.markAllAsRead(chatId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
