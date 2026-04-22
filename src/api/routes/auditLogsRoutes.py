from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, Union
from datetime import datetime, timezone
from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS
from domain.services.auditLogsService import AuditLogsService
from domain.entities.auditLogs import AuditLogs
from schemas.auditLogsSchemas import AuditLogsResponse, AuditLogsCreate, AuditLogsListResponse
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse

import uuid

router = APIRouter(prefix="/logs", tags=["Audit Logs"])


def _logToResponse(log) -> AuditLogsResponse:
    return AuditLogsResponse(
        id=log.id,
        type=log.type,
        catalist=getattr(log, 'catalyst_id', None) or getattr(log, 'catalist_id', None),
        description=log.description,
        timestamps=log.created_at,
        createdAt=log.created_at,
        updatedAt=log.updated_at,
    )


@router.get(
    "",
    response_model=Union[AuditLogsListResponse, PaginatedResponse[AuditLogsResponse]],
    summary="Get all audit logs for current user",
    description="Returns all audit logs for the authenticated user. RLS policies ensure users only see their own logs."
)
def getAllAuditLogs(
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = AuditLogsService(db)

        if paginated:
            result = service.getAll(paginatedParams)
            return PaginatedResponse(
                items=[_logToResponse(log) for log in result.items],
                total=result.total,
                page=result.page,
                pageSize=result.pageSize,
                totalPages=result.totalPages,
                hasNext=result.hasNext,
                hasPrevious=result.hasPrevious,
            )
        else:
            logs = service.getAll()
            return AuditLogsListResponse(
                auditLogs=[_logToResponse(log) for log in logs],
                total=len(logs),
            )

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/{logId}",
    response_model=AuditLogsResponse,
    summary="Get audit log by ID",
    description="Returns a specific audit log by its ID."
)
def getAuditLogById(
    logId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = AuditLogsService(db)
        log = service.get(logId)
        return _logToResponse(log)

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/type/{logType}",
    response_model=Union[AuditLogsListResponse, PaginatedResponse[AuditLogsResponse]],
    summary="Get audit logs by type",
    description="Returns all audit logs filtered by type (e.g., 1=login, 2=password_change)."
)
def getAuditLogsByType(
    logType: int,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = AuditLogsService(db)

        if paginated:
            result = service.getByType(logType, paginatedParams)
            return PaginatedResponse(
                items=[_logToResponse(log) for log in result.items],
                total=result.total,
                page=result.page,
                pageSize=result.pageSize,
                totalPages=result.totalPages,
                hasNext=result.hasNext,
                hasPrevious=result.hasPrevious,
            )
        else:
            logs = service.getByType(logType)
            return AuditLogsListResponse(
                auditLogs=[_logToResponse(log) for log in logs],
                total=len(logs),
            )

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/catalyst/{catalystId}",
    response_model=Union[AuditLogsListResponse, PaginatedResponse[AuditLogsResponse]],
    summary="Get audit logs by catalyst",
    description="Returns all audit logs for a specific catalyst (user)."
)
def getAuditLogsByCatalyst(
    catalystId: str,
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = AuditLogsService(db)

        if paginated:
            result = service.getByCatalyst(catalystId, paginatedParams)
            return PaginatedResponse(
                items=[_logToResponse(log) for log in result.items],
                total=result.total,
                page=result.page,
                pageSize=result.pageSize,
                totalPages=result.totalPages,
                hasNext=result.hasNext,
                hasPrevious=result.hasPrevious,
            )
        else:
            logs = service.getByCatalyst(catalystId)
            return AuditLogsListResponse(
                auditLogs=[_logToResponse(log) for log in logs],
                total=len(logs),
            )

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/range/by-date",
    response_model=Union[AuditLogsListResponse, PaginatedResponse[AuditLogsResponse]],
    summary="Get audit logs by date range",
    description="Returns all audit logs within a specified date range."
)
def getAuditLogsByDateRange(
    startDate: str = Query(..., description="Start date (YYYY-MM-DD)"),
    endDate: str = Query(..., description="End date (YYYY-MM-DD)"),
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = AuditLogsService(db)

        if paginated:
            result = service.getByDateRange(startDate, endDate, paginatedParams)
            return PaginatedResponse(
                items=[_logToResponse(log) for log in result.items],
                total=result.total,
                page=result.page,
                pageSize=result.pageSize,
                totalPages=result.totalPages,
                hasNext=result.hasNext,
                hasPrevious=result.hasPrevious,
            )
        else:
            logs = service.getByDateRange(startDate, endDate)
            return AuditLogsListResponse(
                auditLogs=[_logToResponse(log) for log in logs],
                total=len(logs),
            )

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post(
    "",
    response_model=AuditLogsResponse,
    status_code=201,
    summary="Create audit log",
    description="Creates a new audit log entry."
)
def createAuditLog(
    request: AuditLogsCreate,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = AuditLogsService(db)

        newLog = AuditLogs(
            id=str(uuid.uuid4()),
            type=request.type,
            catalist_id=str(request.catalist),
            catalist=request.catalist,
            description=request.description,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        createdLog = service.create(newLog)
        return _logToResponse(createdLog)

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.put(
    "/update/{logId}/status/{status}",
    response_model=AuditLogsResponse,
    status_code=200,
    summary="Update an audit log status",
    description="Updates the status of an existing audit log."
)
def updateAuditLogStatus(
    status: str,
    logId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    try:
        service = AuditLogsService(db)
        updatedLog = service.updateStatus(logId, status)
        return _logToResponse(updatedLog)

    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
