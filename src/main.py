import os, sys

sys.path.insert(0, os.path.dirname(__file__))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import database
from security.middleware import RateLimitMiddleware, SecurityHeadersMiddleware

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.status import HTTP_200_OK


app = FastAPI(
    title="NoHarm API",
    version="1.0.0",
    debug=config.DEBUG
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.exception_handler(NoHarmException)
def noHarmExceptionHandler(request: Request, exc: NoHarmException):
    return JSONResponse(status_code=exc.statusCode, content=exc.toDict())


@app.get("/")
def __redirect_to_docs():
    return RedirectResponse(url="/docs")


@app.get("/health",
    name="health_check",
    summary="Checa o status da API",
    status_code=HTTP_200_OK,
    responses={HTTP_200_OK: {"status": "ok", "database": "database is connected or disconnected", "env": "config mode [development, production]"}},
)
def healthCheck():
    # Testa a conexão em tempo real
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