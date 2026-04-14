from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from domain.entities.auditLogs import AuditLogs
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from core.database import Database
from typing import Optional


class AuditLogsService:
    def __init__(self, db):
        self.database: Database = db
        self.auditLogsRepository = AuditLogsRepository(self.database)
    
    
    def getAll(self, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
        """
        Return all audit logs, optionally paginated.

        Args:
            params: Optional pagination parameters

        Returns:
            list[AuditLogs] | PaginatedResponse[AuditLogs]
        """
        return self.auditLogsRepository.findAll(params)
    
    
    def get(self, auditLogId: str) -> AuditLogs:
        """
        Return an audit log by ID.
        
        Args:
            auditLogId: ID of the audit log
            
        Returns:
            AuditLogs: audit log
        """
        return self.auditLogsRepository.findById(auditLogId)
    
    
    def create(self, newAuditLog: AuditLogs) -> AuditLogs:
        """
        Create an audit log.
        
        Args:
            newAuditLog: audit log to create
            
        Returns:
            AuditLogs: created audit log
        """
        return self.auditLogsRepository.create(newAuditLog)
        
        
    def getByCatalyst(self, catalistId: str, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
        """
        Return all audit logs by catalyst, optionally paginated.

        Args:
            catalistId: ID of the catalyst
            params: Optional pagination parameters

        Returns:
            list[AuditLogs] | PaginatedResponse[AuditLogs]
        """
        return self.auditLogsRepository.findByCatalystId(catalistId, params)
    
    
    def getByDateRange(self, startDate: str, endDate: str, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
        """
        Return all audit logs within a date range, optionally paginated.

        Args:
            startDate: start date (YYYY-MM-DD)
            endDate: end date (YYYY-MM-DD)
            params: Optional pagination parameters

        Returns:
            list[AuditLogs] | PaginatedResponse[AuditLogs]
        """
        from datetime import datetime
        start = datetime.strptime(startDate, "%Y-%m-%d")
        end = datetime.strptime(endDate, "%Y-%m-%d")
        return self.auditLogsRepository.findByDateRange(start, end, params)
    
    
    def getByType(self, type: int, params: Optional[PaginationParams] = None) -> list[AuditLogs] | PaginatedResponse[AuditLogs]:
        """
        Return all audit logs of a specific type, optionally paginated.

        Args:
            type: type of the audit log (ex: 1 login, 2 password change, etc.)
            params: Optional pagination parameters

        Returns:
            list[AuditLogs] | PaginatedResponse[AuditLogs]
        """
        return self.auditLogsRepository.findByType(type, params)


    def updateStatus(self, id: str, status: int) -> AuditLogs:
        """
        Update the status of an audit log.

        Args:
            id: Audit log ID
            status: New status (ex: enabled, disabled)

        Returns:
            AuditLogs: Updated audit log
        """
        return self.auditLogsRepository.updateStatus(id, status)

