from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from domain.services.messageService import MessageService
from schemas.messageSchemas import MessageCreate, MessageResponse, MessageListResponse
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from domain.entities.message import Message
from typing import Union

import uuid

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.get(
    "/chat/{chatId}",
    response_model=Union[PaginatedResponse[MessageResponse], MessageListResponse],
    summary="Get all messages by chat",
    description="Returns all messages for a given chat, optionally paginated."
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
    summary="Get unread messages by chat",
    description="Returns all unread messages for a given chat, optionally paginated."
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
    description="Returns a specific message by its ID."
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


@router.post(
    "",
    response_model=MessageResponse,
    status_code=201,
    summary="Send a message",
    description="Creates a new message in a chat."
)
def createMessage(
    request: MessageCreate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        newMessage = Message(
            id=str(uuid.uuid4()),
            chat=str(request.chat),
            sender=str(request.sender),
            message=request.message,
            status=request.status,
            send_at=None,
            recived_at=None,
            created_at=None,
            updated_at=None
        )
        return service.create(newMessage)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{messageId}/read",
    response_model=MessageResponse,
    status_code=200,
    summary="Mark message as read",
    description="Marks a specific message as read."
)
def markMessageAsRead(
    messageId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        return service.markAsRead(messageId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/chat/{chatId}/read",
    status_code=200,
    summary="Mark all messages as read",
    description="Marks all messages in a chat as read."
)
def markAllMessagesAsRead(
    chatId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        return service.markAllAsRead(chatId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{messageId}/status/{status}",
    response_model=MessageResponse,
    status_code=200,
    summary="Update message status",
    description="Updates the status of a specific message."
)
def updateMessageStatus(
    messageId: str,
    status: int,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = MessageService(db)
        return service.updateStatus(messageId, status)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
