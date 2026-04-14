from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDbWithRLS
from domain.services.chatService import ChatService
from schemas.chatSchemas import ChatResponse, ChatListResponse
from exceptions.baseExceptions import NoHarmException
from pydantic import BaseModel


router = APIRouter(prefix="/chats", tags=["Chats"])


class ChatCreateRequest(BaseModel):
    receiverId: str


# ── list ──────────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=ChatListResponse,
    summary="Get my chats",
    description="Returns all chats where the authenticated user is a participant."
)
def getMyChats(
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
    description="Returns a specific chat. Only participants may access it (§4.3)."
)
def getChatById(
    chatId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        chat = service.get(chatId, currentUserId)
        return chat
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── create ────────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ChatResponse,
    status_code=201,
    summary="Start or retrieve a chat",
    description=(
        "Opens a chat with another user (§4.1). "
        "Users must be accepted friends (§3.4). "
        "If an active chat already exists between the two users, it is returned instead of creating a duplicate. "
        "New chats start with status = pending."
    )
)
def getOrCreateChat(
    request: ChatCreateRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        chat = service.getOrCreate(currentUserId, request.receiverId)
        return chat
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── activate ──────────────────────────────────────────────────────────────────

@router.post(
    "/{chatId}/accept",
    response_model=ChatResponse,
    status_code=200,
    summary="Accept a chat invitation",
    description=(
        "Activates a pending chat (pending → enabled). "
        "Either participant may accept. Once enabled, messages can be sent (§4.1, §5.1)."
    )
)
def acceptChat(
    chatId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        return service.activate(chatId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── end ───────────────────────────────────────────────────────────────────────

@router.post(
    "/{chatId}/end",
    response_model=ChatResponse,
    status_code=200,
    summary="End a chat",
    description=(
        "Closes the chat (§4.2). Either participant may end it. "
        "Sets endedAt = now and status = disabled. "
        "No new messages can be sent afterwards."
    )
)
def endChat(
    chatId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        return service.endChat(chatId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


# ── delete ────────────────────────────────────────────────────────────────────

@router.delete(
    "/{chatId}",
    status_code=200,
    summary="Delete a chat",
    description="Soft-deletes an existing chat."
)
def deleteChat(
    chatId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = ChatService(db)
        return service.delete(chatId, currentUserId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
