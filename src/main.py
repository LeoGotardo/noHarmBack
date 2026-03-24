from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import database

# Importa todos os models para o SQLAlchemy reconhecer as tabelas
from infrastructure.database.models import (
    userModel,
    streakModel,
    chatModel,
    messageModel,
    badgeModel,
    frendshipModel,
    userBedgesModel,
    auditLogsModel,
)
from infrastructure.external.storageService import Base

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
async def noHarmExceptionHandler(request: Request, exc: NoHarmException):
    return JSONResponse(status_code=exc.statusCode, content=exc.toDict())

@app.get("/health")
async def healthCheck():
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