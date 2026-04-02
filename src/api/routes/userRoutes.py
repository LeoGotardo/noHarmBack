from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.userService import UserService
from schemas.userSchemas import UserCreate, UserUpdate, UserResponse, UserListResponse
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
from domain.entities.user import User
from typing import Union

import uuid


router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=Union[PaginatedResponse[User], UserListResponse],
    summary="Get all users",
    description="Returns all users.")
def getAllUsers(
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get all users.

    Returns:
        UserListResponse: List of users
    """
    try:
        service = UserService(db)
        
        if paginated:
            users = service.findAll(paginatedParams)
            
            return users
        else:
            users = service.findAll()
            
            return UserListResponse(
                users=users,
                total=len(users)
            )

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.get(
    "/{userId}",
    response_model=UserResponse,
    summary="Get a user by ID",
    description="Returns a specific user by its ID.")
def getUserById(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get a specific user by ID.

    Args:
        userId: UUID of the user

    Returns:
        UserResponse: The user details
    """
    try:
        service = UserService(db)
        user = service.findById(userId)
        
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            status=user.status,
            createdAt=user.created_at,
            updatedAt=user.updated_at
        )
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.post("",
             response_model=UserResponse,
             status_code=201,
             summary="Create a user",
             description="Creates a new user.")
def createUser(
    request: UserCreate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Create a new user.

    Args:
        request: User creation data

    Returns:
        UserResponse: The created user
    """
    try:
        service = UserService(db)

        # Create the user entity
        newUser = User(
            id=str(uuid.uuid4()),
            username=request.username,
            email=request.email,
            status=request.status,
            profile_picture=request.profile_picture
        )

        createdUser = service.create(newUser)
        return createdUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.put("/{userId}",
            response_model=UserResponse,
            status_code=200,
            summary="Update a user",
            description="Updates an existing user.")
def updateUser(
    userId: str,
    request: UserUpdate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update an existing user.

    Args:
        userId: UUID of the user
        request: User update data

    Returns:
        UserResponse: The updated user
    """
    try:
        service = UserService(db)
        
        # Update the user entity
        updatedUser = User(
            id=userId,
            username=request.username,
            email=request.email,
            status=request.status,
            profile_picture=request.profile_picture
        )

        updatedUser = service.update(userId, updatedUser)
        return updatedUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.put("/{userId}/status/{status}",
            response_model=UserResponse,
            status_code=200,
            summary="Update a user status",
            description="Updates the status of an existing user.")
def updateUserStatus(
    status: str,
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update the status of an existing user.

    Args:
        status: New status (ex: enabled, disabled)
        userId: UUID of the user

    Returns:
        UserResponse: The updated user
    """
    try:
        service = UserService(db)

        updatedUser = service.updateStatus(userId, status)
        return updatedUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    
    
@router.delete("/{userId}",
            response_model=UserResponse,
            status_code=200,
            summary="Delete a user",
            description="Soft deletes an existing user.")
def deleteUser(
    userId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Delete an existing user.

    Args:
        userId: UUID of the user

    Returns:
        UserResponse: The deleted user
    """
    try:
        service = UserService(db)
        deletedUser = service.delete(userId)
        return deletedUser
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)