import os, sys

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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


app = FastAPI(
    title="NoHarm API",
    version="1.0.0",
    debug=config.DEBUG
)

app.state.limiter = limiter

app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
_IS_DEV = config.EXEC_MODE == "development"


def _corsHeaders(request: Request) -> dict:
    origin = request.headers.get("origin", "")
    allowed = config.ALLOWED_ORIGINS
    if origin and (origin in allowed or "*" in allowed):
        return {"Access-Control-Allow-Origin": origin}
    return {}


@app.exception_handler(NoHarmException)
def noHarmExceptionHandler(request: Request, exc: NoHarmException):
    headers = _corsHeaders(request)
    if not _IS_DEV and exc.statusCode >= 500:
        return JSONResponse(status_code=exc.statusCode, content=_GENERIC_500, headers=headers)
    return JSONResponse(status_code=exc.statusCode, content=exc.toDict(), headers=headers)


@app.exception_handler(Exception)
def genericExceptionHandler(request: Request, exc: Exception):
    headers = _corsHeaders(request)
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