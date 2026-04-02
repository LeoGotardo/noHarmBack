from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.authService import AuthService
from schemas.authSchemas import AuthResponse, AuthRegisterRequest, AuthLoginRequest, AuthRefreshRequest, AuthLogoutRequest
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from typing import Optional, Union
from domain.entities.user import User
from core.config import config

import uuid

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "",
    response_model=Union[AuthResponse, User],
    status_code=201,
    summary="Register a new user",
    description="Creates a new user."
)
def registerUser(
    request: AuthRegisterRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Register a new user.

    Args:
        request: Auth registration data

    Returns:
        Union[AuthResponse, User]: The created user
    """
    try:
        service = AuthService(db)

        # Create the user entity
        newUser = User(
            id=str(uuid.uuid4()),
            username=request.username,
            email=request.email,
            status=request.status,
            profile_picture=request.profile_picture
        )

        createdUser = service.register(newUser)
        return createdUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.post(
    "/login",
    response_model=Union[AuthResponse, User],
    status_code=201,
    summary="Login a user",
    description="Logs in a user."
)
def loginUser(
    request: AuthLoginRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Login a user.

    Args:
        request: Auth login data

    Returns:
        Union[AuthResponse, User]: The logged in user
    """
    try:
        service = AuthService(db)

        # Create the user entity
        newUser = User(
            id=str(uuid.uuid4()),
            username=request.username,
            email=request.email,
            status=request.status,
            profile_picture=request.profile_picture
        )

        createdUser = service.login(newUser)
        return createdUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.post(
    "/refresh",
    response_model=Union[AuthResponse, User],
    status_code=201,
    summary="Refresh a user's access token",
    description="Refreshes a user's access token."
)
def refreshToken(
    request: AuthRefreshRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Refresh a user's access token.

    Args:
        request: Auth refresh data

    Returns:
        Union[AuthResponse, User]: The refreshed user
    """
    try:
        service = AuthService(db)

        # Create the user entity
        newUser = User(
            id=str(uuid.uuid4()),
            username=request.username,
            email=request.email,
            status=request.status,
            profile_picture=request.profile_picture
        )

        createdUser = service.refresh(newUser)
        return createdUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.post(
    "/logout",
    response_model=Union[AuthResponse, User],
    status_code=201,
    summary="Logout a user",
    description="Logs out a user."
)
def logoutUser(
    request: AuthLogoutRequest,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Logout a user.

    Args:
        request: Auth logout data

    Returns:
        Union[AuthResponse, User]: The logged out user
    """
    try:
        service = AuthService(db)

        # Create the user entity
        newUser = User(
            id=str(uuid.uuid4()),
            username=request.username,
            email=request.email,
            status=request.status,
            profile_picture=request.profile_picture
        )

        createdUser = service.logout(newUser)
        return createdUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.get(
    "/me",
    response_model=Union[AuthResponse, User],
    summary="Get current user",
    description="Returns the current user."
)
def getCurrentUser(
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get the current user.

    Returns:
        Union[AuthResponse, User]: The current user
    """
    try:
        service = AuthService(db)
        user = service.getCurrentUser()
        return user
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)