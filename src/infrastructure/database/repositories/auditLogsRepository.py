from infrastructure.database.models.auditLogsModel import AuditLogsModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.auditLogs import AuditLogs

from core.database import Database
from core.config import config


from datetime import datetime

import sys


class AuditLogsRepository(AuditLogs):
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
    
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