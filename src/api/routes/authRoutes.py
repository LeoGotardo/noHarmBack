from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from api.dependencies.database import getDb
from domain.services.authService import AuthService
from exceptions.baseExceptions import NoHarmException
from schemas.authSchemas import AuthLoginRequest, AuthRefreshRequest, AuthResponse, AuthRegisterRequest

router = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer()


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    summary="Register a new user",
    description=(
        "Creates a new account from Firebase identity data and returns a token pair. "
        "Enforces username uniqueness, email uniqueness, and username format rules. "
        "Status is set to 'pending' until email is verified by Firebase."
    )
)
def register(request: AuthRegisterRequest, db: Session = Depends(getDb)):
    try:
        service = AuthService(db)
        tokens = service.register(request)
        return AuthResponse(**tokens)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login",
    description=(
        "Authenticates the user via Firebase UID and issues a token pair. "
        "Rate-limited to 5 attempts / 15 min per UID. "
        "Banned, blocked, or deleted accounts are rejected with 403."
    )
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
    description="Issues a new token pair from a valid refresh token. The old refresh token is revoked (rotation)."
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
    refreshRequest: AuthRefreshRequest,
    accessCredentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(getDb)
):
    try:
        service = AuthService(db)
        service.logout(accessCredentials.credentials, refreshRequest.refreshToken)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
