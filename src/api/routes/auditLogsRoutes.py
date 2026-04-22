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


@router.get(
    "",
    response_model=Union[AuditLogsListResponse, PaginatedResponse[AuditLogs]],
    summary="Get all audit logs for current user",
    description="Returns all audit logs for the authenticated user. RLS policies ensure users only see their own logs."
)
def getAllAuditLogs(
    paginated: bool = False,
    paginatedParams: PaginationParams = Depends(),
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Get all audit logs for the current authenticated user.
    
    Args:
        paginated: If true, returns a paginated response

    Returns:
        AuditLogsListResponse: List of audit logs with total count
    """
    try:
        service = AuditLogsService(db)
        
        if paginated:
            logs = service.getAll(paginatedParams)
            
            return logs
        else:
            logs = service.getAll()

            return AuditLogsListResponse(
                auditLogs=logs,
                total=len(logs)
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
    """
    Get a specific audit log by ID.

    Args:
        logId: UUID of the audit log

    Returns:
        AuditLogsResponse: The audit log details
    """
    try:
        service = AuditLogsService(db)
        log = service.get(logId)
        
        return AuditLogsResponse(
            catalist=log.catalist_id,
            timestamps=log.created_at,
            description=log.description,
            id=log.id,
            type=log.type,
        )
    
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/type/{logType}",
    response_model=Union[AuditLogsListResponse, PaginatedResponse[AuditLogs]],
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
    """
    Get audit logs filtered by type.

    Args:
        logType: Type code of the audit log
        paginated: If true, returns a paginated response
        paginatedParams: Pagination parameters

    Returns:
        AuditLogsListResponse: List of matching audit logs
    """
    try:
        service = AuditLogsService(db)
        
        if paginated:
            logs = service.getByType(logType, paginatedParams)
            
            return logs
        else:
            logs = service.getAll()

            return AuditLogsListResponse(
                auditLogs=logs,
                total=len(logs)
            )
            
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/catalyst/{catalystId}",
    response_model=Union[AuditLogsListResponse, PaginatedResponse[AuditLogs]],
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
    """
    Get audit logs filtered by catalyst ID.

    Args:
        catalystId: UUID of the catalyst user
        paginated: If true, returns a paginated response
        paginatedParams: Pagination parameters

    Returns:
        AuditLogsListResponse: List of matching audit logs
    """
    try:
        service = AuditLogsService(db)
        
        if paginated:
            logs = service.getByCatalyst(catalystId, paginatedParams)
        
            return logs
        else:
            logs = service.getAll()

            return AuditLogsListResponse(
                auditLogs=logs,
                total=len(logs)
            )
            
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/range/by-date",
    response_model=Union[AuditLogsListResponse, PaginatedResponse[AuditLogs]],
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
    """
    Get audit logs filtered by date range.

    Args:
        startDate: Start date in YYYY-MM-DD format
        endDate: End date in YYYY-MM-DD format

    Returns:
        AuditLogsListResponse: List of audit logs within the date range
    """
    try:
        service = AuditLogsService(db)
        
        if paginated:
            logs = service.getByDateRange(startDate, endDate, paginatedParams)
        
            return logs
        else:
            logs = service.getAll()

            return AuditLogsListResponse(
                auditLogs=logs,
                total=len(logs)
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
    """
    Create a new audit log.

    Args:
        request: Audit log creation data

    Returns:
        AuditLogsResponse: The created audit log
    """
    try:
        service = AuditLogsService(db)

        # Create the audit log entity
        newLog = AuditLogs(
            id=str(uuid.uuid4()),
            type=request.type,
            catalist_id=str(request.catalist),
            catalist=request.catalist,
            description=request.description,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat()
        )

        createdLog = service.create(newLog)
        return createdLog
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
    

@router.put("/update/{logId}/status/{status}",
            response_model=AuditLogsResponse,
            status_code=200,
            summary="Update an audit log status",
            description="Updates the status of an existing audit log.")
def updateAuditLogStatus(
    status: str,
    logId: str,
    db: Session = Depends(getDbWithRLS),
    currentUserId: str = Depends(getCurrentUser)
):
    """
    Update the status of an existing audit log.

    Args:
        status: New status (ex: enabled, disabled)
        logId: UUID of the audit log

    Returns:
        AuditLogsResponse: The updated audit log
    """
    try:
        service = AuditLogsService(db)

        updatedLog = service.updateStatus(logId, status)
        return updatedLog
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
