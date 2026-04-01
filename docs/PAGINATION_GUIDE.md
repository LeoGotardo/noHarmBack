# Pagination System Guide

This document explains the pagination system implemented for the noHarmBack API.

## Files Created

### 1. `src/schemas/paginationSchemas.py`
Defines the pagination schemas and utilities:

- `PaginationParams` - Query parameters (page, pageSize) with validation
- `PaginatedResponse[T]` - Generic response wrapper with metadata
- `createPaginatedResponse()` - Helper to build paginated responses

### 2. `src/infrastructure/database/paginationUtils.py`
Database-level pagination utilities:

- `paginateQuery()` - Apply pagination to SQLAlchemy queries
- `getPaginatedResult()` - Execute query and return PaginatedResponse
- `PaginatedRepository` - Mixin class for repositories

### 3. Updated `src/infrastructure/database/repositories/auditLogsRepository.py`
Added paginated methods:
- `findAllPaginated()`
- `findByTypePaginated()`
- `findByCatalystIdPaginated()`
- `findByDateRangePaginated()`

### 4. Updated `src/domain/services/auditLogsService.py`
Added paginated service methods:
- `getAllPaginated()`
- `getByTypePaginated()`
- `getByCatalystPaginated()`
- `getByDateRangePaginated()`

## How to Apply Pagination to Routes

Replace the existing auditLogsRoutes.py with this pagination-enabled version:

```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from api.dependencies.database import getDbWithRLS
from domain.services.auditLogsService import AuditLogsService
from domain.entities.auditLogs import AuditLogs
from schemas.auditLogsSchemas import AuditLogsResponse, AuditLogsCreate
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from exceptions.baseExceptions import NoHarmException
import uuid

router = APIRouter(prefix="/logs", tags=["Audit Logs"])


@router.get(
    "",
    response_model=PaginatedResponse[AuditLogsResponse],
    summary="Get all audit logs for current user",
)
def getAllAuditLogs(
    db: Session = Depends(getDbWithRLS),
    pagination: PaginationParams = Depends(),
):
    """Get paginated audit logs."""
    try:
        service = AuditLogsService(db)
        return service.getAllPaginated(pagination)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get("/{logId}", response_model=AuditLogsResponse)
def getAuditLogById(logId: str, db: Session = Depends(getDbWithRLS)):
    """Get a specific audit log by ID."""
    try:
        service = AuditLogsService(db)
        return service.get(logId)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/type/{logType}",
    response_model=PaginatedResponse[AuditLogsResponse],
)
def getAuditLogsByType(
    logType: int,
    db: Session = Depends(getDbWithRLS),
    pagination: PaginationParams = Depends(),
):
    """Get paginated audit logs by type."""
    try:
        service = AuditLogsService(db)
        return service.getByTypePaginated(logType, pagination)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/catalyst/{catalystId}",
    response_model=PaginatedResponse[AuditLogsResponse],
)
def getAuditLogsByCatalyst(
    catalystId: str,
    db: Session = Depends(getDbWithRLS),
    pagination: PaginationParams = Depends(),
):
    """Get paginated audit logs by catalyst."""
    try:
        service = AuditLogsService(db)
        return service.getByCatalystPaginated(catalystId, pagination)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.get(
    "/range/by-date",
    response_model=PaginatedResponse[AuditLogsResponse],
)
def getAuditLogsByDateRange(
    startDate: str = Query(..., description="Start date (YYYY-MM-DD)"),
    endDate: str = Query(..., description="End date (YYYY-MM-DD)"),
    db: Session = Depends(getDbWithRLS),
    pagination: PaginationParams = Depends(),
):
    """Get paginated audit logs by date range."""
    try:
        service = AuditLogsService(db)
        return service.getByDateRangePaginated(startDate, endDate, pagination)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)


@router.post("", response_model=AuditLogsResponse, status_code=201)
def createAuditLog(
    request: AuditLogsCreate,
    db: Session = Depends(getDbWithRLS),
):
    """Create a new audit log."""
    try:
        service = AuditLogsService(db)
        newLog = AuditLogs(
            id=str(uuid.uuid4()),
            type=request.type,
            catalist_id=str(request.catalist),
            catalist=request.type,
            description=request.description,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat()
        )
        return service.create(newLog)
    except NoHarmException as e:
        raise HTTPException(status_code=e.statusCode, detail=e.message)
```

## Usage Examples

### Request with pagination:
```bash
# Get page 2 with 50 items per page
GET /logs?page=2&pageSize=50

# Get logs by type with pagination
GET /logs/type/1?page=1&pageSize=20

# Get logs by date range with pagination
GET /logs/range/by-date?startDate=2025-01-01&endDate=2025-03-31&page=1&pageSize=10
```

### Response format:
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "pageSize": 20,
  "totalPages": 5,
  "hasNext": true,
  "hasPrevious": false
}
```

## Default Values

- `page`: 1 (first page)
- `pageSize`: 20 items per page
- `pageSize` maximum: 100 items

## Applying Pagination to Other Repositories

To add pagination to other repositories (e.g., userRepository, streakRepository):

1. Import the pagination utilities:
```python
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse
```

2. Add a paginated method:
```python
def findAllPaginated(self, params: PaginationParams) -> PaginatedResponse[User]:
    query = self.session.query(UserModel)
    total = query.count()
    offset = (params.page - 1) * params.pageSize
    items = query.offset(offset).limit(params.pageSize).all()
    return createPaginatedResponse(items, total, params.page, params.pageSize)
```

3. Add corresponding service method and route.

## Benefits

1. **Consistent API**: All paginated endpoints return the same response structure
2. **Type Safety**: Generic `PaginatedResponse[T]` maintains type information
3. **Easy Integration**: Just add `pagination: PaginationParams = Depends()` to route parameters
4. **Performance**: Database-level pagination with OFFSET/LIMIT
5. **Metadata**: Clients get total count, total pages, and navigation hints (hasNext, hasPrevious)
