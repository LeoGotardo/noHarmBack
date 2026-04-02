from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.friendshipService import FriendshipService
from schemas.friendshipSchemas import FriendshipResponse, FriendshipCreate, FriendshipUpdate, FriendshipListResponse
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from typing import Union, Literal
from domain.entities.friendship import Friendship
from core.config import config

import uuid

router = APIRouter(prefix="/friendships", tags=["Friendships"])


@router.get(
    "",
    response_model=Union[PaginatedResponse[Friendship], FriendshipListResponse],
    summary="Get all friendships for current user",
    description="Returns all friendships where the current user is a sender or receiver."
)
def getFriendshipsByUserId(
    userId: str,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get all friendships for the current user.

    Returns:
        FriendshipListResponse: List of friendships
    """
    try:
        service = FriendshipService(db)
        
        if paginated:
            friendships = service.getByUserId(userId)
            
            return friendships
        else:
            friendships = service.getByUserId(userId)
            
            return FriendshipListResponse(
                friendships=friendships,
                total=len(friendships)
            )
            
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)