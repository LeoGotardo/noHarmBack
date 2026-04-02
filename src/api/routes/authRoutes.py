from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field

from api.dependencies.database import getDb
from domain.services.authService import AuthService
from exceptions.baseExceptions import NoHarmException
from schemas.authSchemas import AuthLoginRequest, AuthRefreshRequest, AuthResponse, AuthRegisterRequest, AuthLogoutRequest

router = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer()


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    summary="Register a new user",
    description="Creates a new account and returns a token pair."
)
def register(request: AuthRegisterRequest, db: Session = Depends(getDb)):
    try:
        service = AuthService(db)
        service.register(request)
        tokens = service.login(request)
        return AuthResponse(**tokens)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login",
    description="Authenticates the user and returns a token pair."
)
def login(request: AuthLoginRequest, db: Session = Depends(getDb)):
    try:
        service = AuthService(db)
        tokens = service.login(request)
        return AuthResponse(**tokens)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Refresh tokens",
    description="Issues a new token pair from a valid refresh token. The old refresh token is revoked."
)
def refresh(request: AuthRefreshRequest, db: Session = Depends(getDb)):
    try:
        service = AuthService(db)
        tokens = service.refresh(request.refreshToken)
        return AuthResponse(**tokens)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/logout",
    status_code=204,
    summary="Logout",
    description="Revokes both tokens. The user is logged out of this device only."
)
def logout(
    refreshCredentials: AuthRefreshRequest,
    accessCredentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(getDb)
):
    try:
        service = AuthService(db)
        service.logout(accessCredentials.credentials, refreshCredentials.refreshToken)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)