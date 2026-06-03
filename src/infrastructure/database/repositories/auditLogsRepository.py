from core.errorUtils import excLocation
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.auditLogs import AuditLogs
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database

from datetime import datetime
from typing import Optional


class AuditLogsRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
    def _toEntity(self, model: AuditLogsModel) -> AuditLogs:
        return AuditLogs(
            id=model.id,
            type=model.type,
            catalyst_id=model.catalyst_id if model.catalyst_id else None,
            description=model.description,
            created_at=model.created_at,
            updated_at=model.updated_at,
            catalyst=model.catalyst
        )
        
        
    def findAll(self, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
        """Find all audit logs, optionally paginated

        Args:
            params: Optional pagination parameters

        Returns:
            list[AuditLogs] | PaginatedResponse[AuditLogs]
        """
        try:
            query = self.session.query(AuditLogsModel)
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                items = query.offset(offset).limit(params.pageSize).all()
                items = [self._toEntity(item) for item in items]
                return createPaginatedResponse(items, total, params.page, params.pageSize)  
            
            return [self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def findById(self, id: str) -> AuditLogs:
        """Find an audit log by ID
        
        Args:
            id (str): AuditLogs ID
            
        Returns:
            AuditLogs: AuditLogs with his full data
        """
        try:
            auditLogs = self.session.query(AuditLogsModel).filter(AuditLogsModel.id == id).first()
            if auditLogs:
                return self._toEntity(auditLogs)
            else:
                raise NoHarmException(statusCode=404, message="AuditLogs not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def findByType(self, logType: int, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
        """Find all audit logs by logType, optionally paginated

        Args:
            logType (int): AuditLogs logType
            params: Optional pagination parameters

        Returns:
            list[AuditLogs] | PaginatedResponse[AuditLogs]
        """
        try:
            query = self.session.query(AuditLogsModel).filter(AuditLogsModel.type == logType)
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                items = query.offset(offset).limit(params.pageSize).all()
                items = [self._toEntity(item) for item in items]
                
                return createPaginatedResponse(items, total, params.page, params.pageSize)  
            return [self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def findByCatalystId(self, catalyst_id: str, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
        """Find all audit logs by catalyst ID, optionally paginated

        Args:
            catalyst_id (str): Catalyst ID
            params: Optional pagination parameters

        Returns:
            list[AuditLogs] | PaginatedResponse[AuditLogs]
        """
        try:
            query = self.session.query(AuditLogsModel).filter(AuditLogsModel.catalyst_id == catalyst_id)
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                items = query.offset(offset).limit(params.pageSize).all()
                items = [self._toEntity(item) for item in items]
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            
            return [self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def findByDateRange(self, start: datetime, end: datetime, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
        """Find all audit logs by date range, optionally paginated

        Args:
            start (datetime): Start date
            end (datetime): End date
            params: Optional pagination parameters

        Returns:
            list[AuditLogs] | PaginatedResponse[AuditLogs]
        """
        try:
            query = self.session.query(AuditLogsModel).filter(
                AuditLogsModel.created_at >= start,
                AuditLogsModel.created_at <= end
            )
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                items = query.offset(offset).limit(params.pageSize).all()
                items = [self._toEntity(item) for item in items]
                
                return createPaginatedResponse(items, total, params.page, params.pageSize)  
            return [self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def create(self, AuditLogs: AuditLogs) -> AuditLogs:
        """Create an audit log

        Args:
            AuditLogs (AuditLogs): AuditLogs to create

        Returns:
            AuditLogs: AuditLogs with his full data
        """
        try:
            auditLogsModel = AuditLogsModel(
                type=AuditLogs.type,
                catalyst_id=AuditLogs.catalyst_id,
                description=AuditLogs.description,
                created_at=AuditLogs.created_at,
                updated_at=AuditLogs.updated_at,
                catalyst=AuditLogs.catalyst
            )
            self.session.add(auditLogsModel)
            self.session.commit()
            return AuditLogs
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

