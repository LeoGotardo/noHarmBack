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
        
        
    def findAll(self) -> list[AuditLogs]:
        """Find all audit logs
        
        Returns:
            list[AuditLogs]: List of AuditLogs
        """
        try:
            auditLogs = self.session.query(AuditLogsModel).all()
            return auditLogs
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
        
        
    def findByType(self, type: int) -> list[AuditLogs]:
        """Find all audit logs by type
        
        Args:
            type (int): AuditLogs type
            
        Returns:
            list[AuditLogs]: List of AuditLogs
        """
        try:
            auditLogs = self.session.query(AuditLogsModel).filter(AuditLogsModel.type == type).all()
            return auditLogs
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findByCatalystId(self, catalyst_id: int) -> list[AuditLogs]:
        """Find all audit logs by catalyst ID
        
        Args:
            catalyst_id (str): Catalyst ID
            
        Returns:
            list[AuditLogs]: List of AuditLogs
        """
        try:
            auditLogs = self.session.query(AuditLogsModel).filter(AuditLogsModel.catalyst_id == catalyst_id).all()
            return auditLogs
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findByDateRange(self, start: datetime, end: datetime) -> list[AuditLogs]:
        """Find all audit logs by date range
        
        Args:
            start (datetime): Start date
            end (datetime): End date
            
        Returns:
            list[AuditLogs]: List of AuditLogs
        """
        try:
            auditLogs = self.session.query(AuditLogsModel).filter(AuditLogsModel.created_at >= start, AuditLogsModel.created_at <= end).all()
            return auditLogs
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


    def findAllPaginated(self, params: PaginationParams) -> PaginatedResponse[AuditLogs]:
        """Find all audit logs with pagination

        Args:
            params: Pagination parameters (page, pageSize)

        Returns:
            PaginatedResponse[AuditLogs]: Paginated list of audit logs
        """
        try:
            query = self.session.query(AuditLogsModel)

            # Get total count
            total = query.count()

            # Apply pagination
            offset = (params.page - 1) * params.pageSize
            paginatedQuery = query.offset(offset).limit(params.pageSize)
            logs = paginatedQuery.all()

            return createPaginatedResponse(
                items=logs,
                total=total,
                page=params.page,
                pageSize=params.pageSize
            )
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findByTypePaginated(self, type: int, params: PaginationParams) -> PaginatedResponse[AuditLogs]:
        """Find audit logs by type with pagination

        Args:
            type: Audit log type
            params: Pagination parameters

        Returns:
            PaginatedResponse[AuditLogs]: Paginated list of matching audit logs
        """
        try:
            query = self.session.query(AuditLogsModel).filter(AuditLogsModel.type == type)

            total = query.count()
            offset = (params.page - 1) * params.pageSize
            paginatedQuery = query.offset(offset).limit(params.pageSize)
            logs = paginatedQuery.all()

            return createPaginatedResponse(
                items=logs,
                total=total,
                page=params.page,
                pageSize=params.pageSize
            )
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findByCatalystIdPaginated(self, catalyst_id: str, params: PaginationParams) -> PaginatedResponse[AuditLogs]:
        """Find audit logs by catalyst ID with pagination

        Args:
            catalyst_id: Catalyst ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[AuditLogs]: Paginated list of matching audit logs
        """
        try:
            query = self.session.query(AuditLogsModel).filter(AuditLogsModel.catalyst_id == catalyst_id)

            total = query.count()
            offset = (params.page - 1) * params.pageSize
            paginatedQuery = query.offset(offset).limit(params.pageSize)
            logs = paginatedQuery.all()

            return createPaginatedResponse(
                items=logs,
                total=total,
                page=params.page,
                pageSize=params.pageSize
            )
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findByDateRangePaginated(
        self,
        start: datetime,
        end: datetime,
        params: PaginationParams
    ) -> PaginatedResponse[AuditLogs]:
        """Find audit logs by date range with pagination

        Args:
            start: Start date
            end: End date
            params: Pagination parameters

        Returns:
            PaginatedResponse[AuditLogs]: Paginated list of matching audit logs
        """
        try:
            query = self.session.query(AuditLogsModel).filter(
                AuditLogsModel.created_at >= start,
                AuditLogsModel.created_at <= end
            )

            total = query.count()
            offset = (params.page - 1) * params.pageSize
            paginatedQuery = query.offset(offset).limit(params.pageSize)
            logs = paginatedQuery.all()

            return createPaginatedResponse(
                items=logs,
                total=total,
                page=params.page,
                pageSize=params.pageSize
            )
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')