from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import database

from fastapi.responses import JSONResponse, RedirectResponse
from starlette.status import HTTP_200_OK

# Importa todos os models para o SQLAlchemy reconhecer as tabelas
from infrastructure.database.models import (
    friendshipModel,
    userModel,
    streakModel,
    chatModel,
    messageModel,
    badgeModel,
    userBedgesModel,
    auditLogsModel,
)

import os, sys

sys.path.insert(0, os.path.dirname(__file__))

app = FastAPI(
    title="NoHarm API",
    version="1.0.0",
    debug=config.DEBUG
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    responses={HTTP_200_OK: {"description": "A API está responsiva"}},
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