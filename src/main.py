import os, sys

sys.path.insert(0, os.path.dirname(__file__))

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import database
from security.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from security.limiter import limiter
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.status import HTTP_200_OK

from api.routes.authRoutes import router as authRouter
from api.routes.userRoutes import router as userRouter
from api.routes.chatRoutes import router as chatRouter
from api.routes.messageRoutes import router as messageRouter
from api.routes.streakRoutes import router as streakRouter
from api.routes.badgesRoutes import router as badgesRouter
from api.routes.userBadgesRoutes import router as userBadgesRouter
from api.routes.auditLogsRoutes import router as auditLogsRouter
from api.routes.friendshipRoutes import router as friendshipRouter
from api.routes.notificationRoutes import router as notificationRouter
from websocket.socketManager import socketApp
from websocket import emitter


logging.basicConfig(
    level=logging.DEBUG if config.DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("noharm")


app = FastAPI(
    title="NoHarm API",
    version="1.0.0",
    debug=config.DEBUG
)


@app.on_event("startup")
async def _bindWebsocketLoop():
    """Socket.IO emits from REST handlers run in the threadpool — they need a
    handle on the loop the server is actually running."""
    emitter.bindLoop()

app.state.limiter = limiter

app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(authRouter)
app.include_router(userRouter)
app.include_router(chatRouter)
app.include_router(messageRouter)
app.include_router(streakRouter)
app.include_router(badgesRouter)
app.include_router(userBadgesRouter)
app.include_router(auditLogsRouter)
app.include_router(friendshipRouter)
app.include_router(notificationRouter)


_GENERIC_500 = {"errorCode": "INTERNAL_ERROR", "message": "An internal server error occurred."}
# EXEC_MODE is "dev" / "prod" (see .secrets.toml); "development" never matched.
_IS_DEV = config.EXEC_MODE.lower() in ("dev", "development")

# Every error response uses the same envelope: {errorCode, message, details?}.
# `detail` (FastAPI's default key) is never emitted, so clients read one shape.
_STATUS_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
}


def _corsHeaders(request: Request) -> dict:
    origin = request.headers.get("origin", "")
    allowed = config.ALLOWED_ORIGINS
    if origin and (origin in allowed or "*" in allowed):
        return {"Access-Control-Allow-Origin": origin}
    return {}


def _errorCodeFor(statusCode: int) -> str:
    return _STATUS_ERROR_CODES.get(statusCode, "INTERNAL_ERROR" if statusCode >= 500 else "ERROR")


@app.exception_handler(NoHarmException)
def noHarmExceptionHandler(request: Request, exc: NoHarmException):
    headers = _corsHeaders(request)
    if exc.statusCode >= 500:
        logger.exception("%s %s → %s", request.method, request.url.path, exc.message, exc_info=exc)
        if not _IS_DEV:
            return JSONResponse(status_code=exc.statusCode, content=_GENERIC_500, headers=headers)
    return JSONResponse(status_code=exc.statusCode, content=exc.toDict(), headers=headers)


@app.exception_handler(StarletteHTTPException)
def httpExceptionHandler(request: Request, exc: StarletteHTTPException):
    """Normalise FastAPI's `{"detail": ...}` into the shared envelope."""
    headers = _corsHeaders(request)
    detail = exc.detail
    message = detail if isinstance(detail, str) else "Request failed."
    content = {"errorCode": _errorCodeFor(exc.status_code), "message": message}
    if not isinstance(detail, str):
        content["details"] = detail
    if exc.status_code >= 500:
        logger.error("%s %s → %s", request.method, request.url.path, detail)
    return JSONResponse(status_code=exc.status_code, content=content, headers=headers)


@app.exception_handler(RequestValidationError)
def validationExceptionHandler(request: Request, exc: RequestValidationError):
    headers = _corsHeaders(request)
    return JSONResponse(
        status_code=422,
        content={
            "errorCode": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "details": jsonable_encoder(exc.errors()),
        },
        headers=headers,
    )


@app.exception_handler(Exception)
def genericExceptionHandler(request: Request, exc: Exception):
    headers = _corsHeaders(request)
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    if _IS_DEV:
        import traceback
        return JSONResponse(
            status_code=500,
            content={"errorCode": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}", "details": traceback.format_exc()},
            headers=headers,
        )
    return JSONResponse(status_code=500, content=_GENERIC_500, headers=headers)


@app.get("/")
def __redirect_to_docs():
    return RedirectResponse(url="/docs")


app.mount("/ws", socketApp)


@app.get("/health",
    name="health_check",
    summary="Checa o status da API",
    status_code=HTTP_200_OK,
    responses={HTTP_200_OK: {"status": "ok", "database": "database is connected or disconnected", "env": "config mode [development, production]"}},
)
def healthCheck():
    # Test the connection in real time
    try:
        with database.engine.connect():
            dbStatus = "connected"
    except Exception:
        dbStatus = "disconnected"

    return {
        "status": "ok",
        "database": dbStatus,
        "env": config.EXEC_MODE
    }