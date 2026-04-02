from infrastructure.database.models.auditLogsModel import AuditLogsModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.auditLogs import AuditLogs
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from datetime import datetime
from typing import Optional

import sys


class AuditLogsRepository(AuditLogs):
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
        
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
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            return query.all()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
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
                return auditLogs
            else:
                raise NoHarmException(status_code=404, message="AuditLogs not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def findByType(self, type: int, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
        """Find all audit logs by type, optionally paginated

        Args:
            type (int): AuditLogs type
            params: Optional pagination parameters

        Returns:
            list[AuditLogs] | PaginatedResponse[AuditLogs]
        """
        try:
            query = self.session.query(AuditLogsModel).filter(AuditLogsModel.type == type)
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                items = query.offset(offset).limit(params.pageSize).all()
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            return query.all()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findByCatalystId(self, catalyst_id: int, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
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
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            return query.all()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
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
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            return query.all()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def create(self, AuditLogs: AuditLogs) -> AuditLogs:
        """Create an audit log

        Args:
            AuditLogs (AuditLogs): AuditLogs to create

        Returns:
            AuditLogs: AuditLogs with his full data
        """
        try:
            self.session.add(AuditLogs)
            self.session.commit()
            return AuditLogs
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def updateStatus(self, id: str, status: int) -> AuditLogs:
        """Update the status of an audit log

        Args:
            id: Audit log ID
            status: New status (ex: enabled, disabled)

        Returns:
            AuditLogs: Updated audit log
        """
        try:
            auditLog = self.findById(id)
            auditLog.status = status
            self.session.commit()
            return auditLog
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')

