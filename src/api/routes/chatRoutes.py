from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from domain.services.chatService import ChatService
from schemas.chatSchemas import ChatCreate, ChatUpdate, ChatResponse, ChatListResponse
from exceptions.baseExceptions import NoHarmException
from domain.entities.chat import Chat

import uuid

router = APIRouter(prefix="/chats", tags=["Chats"])


@router.get(
    "",
    response_model=ChatListResponse,
    summary="Get all chats for current user",
    description="Returns all chats where the current user is a participant."
)
def getAllChats(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        chats = service.getAllByUserId(currentUserId)
        return ChatListResponse(chats=chats, total=len(chats))
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{chatId}",
    response_model=ChatResponse,
    summary="Get a chat by ID",
    description="Returns a specific chat by its ID."
)
def getChatById(
    chatId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        chat = service.get(chatId)
        return chat
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "",
    response_model=ChatResponse,
    status_code=201,
    summary="Create a chat",
    description="Creates a new chat between two users."
)
def createChat(
    request: ChatCreate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        newChat = Chat(
            id=str(uuid.uuid4()),
            sender=str(request.sender),
            reciver=str(request.reciver),
            started_at=request.startedAt,
            ended_at=request.endedAt,
            status=request.status,
            messages=[],
            created_at=None,
            updated_at=None
        )
        createdChat = service.create(newChat)
        return createdChat
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{chatId}",
    response_model=ChatResponse,
    status_code=200,
    summary="Update a chat",
    description="Updates an existing chat."
)
def updateChat(
    chatId: str,
    request: ChatUpdate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        updatedChat = Chat(
            id=chatId,
            sender=None,
            reciver=None,
            started_at=None,
            ended_at=request.endedAt,
            status=request.status,
            messages=[],
            created_at=None,
            updated_at=None
        )
        return service.update(chatId, updatedChat)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/{chatId}/status/{status}",
    response_model=ChatResponse,
    status_code=200,
    summary="Update chat status",
    description="Updates the status of an existing chat."
)
def updateChatStatus(
    chatId: str,
    status: int,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        return service.updateStatus(chatId, status)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.delete(
    "/{chatId}",
    status_code=200,
    summary="Delete a chat",
    description="Soft deletes an existing chat."
)
def deleteChat(
    chatId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        return service.delete(chatId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
