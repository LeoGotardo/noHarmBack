from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from api.dependencies.database import getDb
from domain.services.authService import AuthService
from exceptions.baseExceptions import NoHarmException
from schemas.authSchemas import (
    AuthLoginRequest,
    AuthReactivateRequest,
    AuthRefreshRequest,
    AuthResponse,
    AuthRegisterRequest,
)
from security.limiter import limiter

router = APIRouter(prefix="/auth", tags=["Auth"])
security = HTTPBearer()


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=201,
    summary="Register a new user",
    description=(
        "Creates a new account from a verified Firebase ID token and returns a token pair. "
        "The uid, email and email-verified flag are read from the token's claims — the body "
        "carries only the token and the chosen username. "
        "Enforces username uniqueness, email uniqueness, and username format rules. "
        "Status is set to 'pending' until email is verified by Firebase."
    )
)
@limiter.limit("5/minute")
def register(request: Request, body: AuthRegisterRequest, db: Session = Depends(getDb)):
    # NoHarmException is deliberately not converted to HTTPException here.
    # The handler in main.py serialises it with `errorCode` and `details`
    # intact, and ACCOUNT_PENDING_DELETION carries the restore deadline in
    # `details` — flattening it to `detail=e.message` would leave the client
    # unable to tell "restore your account?" from "registration failed".
    service = AuthService(db)
    tokens = service.register(body)
    return AuthResponse(**tokens)


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login",
    description=(
        "Verifies the Firebase ID token and issues a token pair for the UID it carries. "
        "Rate-limited to 5 attempts / 15 min per UID. "
        "Banned and blocked accounts are rejected with 403. A deleted account still inside "
        "its grace window answers 403 ACCOUNT_PENDING_DELETION with `details.deletionScheduledAt`, "
        "which POST /auth/reactivate can undo; past the window it is 403 ACCOUNT_DELETED."
    )
)
@limiter.limit("10/minute")
def login(request: Request, body: AuthLoginRequest, db: Session = Depends(getDb)):
    # Uncaught on purpose — see the note on register().
    service = AuthService(db)
    tokens = service.login(body)
    return AuthResponse(**tokens)


@router.post(
    "/reactivate",
    response_model=AuthResponse,
    summary="Restore a deleted account",
    description=(
        "Restores an account that was soft-deleted and is still inside its grace window, "
        "and returns a token pair. Requires a Firebase ID token for that UID — the same proof "
        "login requires. Banned accounts are refused, an active account is a 409, and an "
        "account whose window has closed answers 403 ACCOUNT_DELETED like any missing one."
    )
)
@limiter.limit("5/minute")
def reactivate(request: Request, body: AuthReactivateRequest, db: Session = Depends(getDb)):
    service = AuthService(db)
    tokens = service.reactivate(body.idToken)
    return AuthResponse(**tokens)


@router.post(
    "/refresh",
    response_model=AuthResponse,
    summary="Refresh tokens",
    description="Issues a new token pair from a valid refresh token. The old refresh token is revoked (rotation)."
)
@limiter.limit("20/minute")
def refresh(request: Request, body: AuthRefreshRequest, db: Session = Depends(getDb)):
    # Uncaught, like register() and login(): a client refreshing into a 403
    # needs to know whether the account is banned, blocked or mid-deletion, and
    # the HTTPException conversion collapses all three into "FORBIDDEN".
    service = AuthService(db)
    tokens = service.refresh(body.refreshToken)
    return AuthResponse(**tokens)


@router.post(
    "/logout",
    status_code=204,
    summary="Logout",
    description="Revokes both tokens. The user is logged out of this device only."
)
@limiter.limit("20/minute")
def logout(
    request: Request,
    body: AuthRefreshRequest,
    accessCredentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(getDb)
):
    try:
        service = AuthService(db)
        service.logout(accessCredentials.credentials, body.refreshToken)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
