from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from domain.entities.auditLogs import AuditLogs
from core.database import Database


class AuditLogsService:
    def __init__(self, db):
        self.database: Database = db
        self.auditLogsRepository = AuditLogsRepository(self.database)
    
    
    def getAll(self) -> list[AuditLogs]:
        """
        Return all audit logs.
        
        Returns:
            list[AuditLogs]: list of audit logs
        """
        return self.auditLogsRepository.findAll()
    
    
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
        
        
    def getByCatalyst(self, catalistId: str) -> list[AuditLogs]:
        """
        Return all audit logs by catalist.
        
        Args:
            catalistId: ID of the catalist
            
        Returns:
            list[AuditLogs]: list of audit logs
        """
        return self.auditLogsRepository.findByCatalystId(catalistId)
    
    
    def getByDateRange(self, startDate: str, endDate: str) -> list[AuditLogs]:
        """
        Return all audit logs within a date range.
        
        Args:
            startDate: start date (YYYY-MM-DD)
            endDate: end date (YYYY-MM-DD)
            
        Returns:
            list[AuditLogs]: list of audit logs
        """
        return self.auditLogsRepository.findByDateRange(startDate, endDate)
    
    
    def getByType(self, type: int) -> list[AuditLogs]:
        """
        Return all audit logs of a specific type.
        
        Args:
            type: type of the audit log (ex: 1 login, 2 password change, etc.)
            
        Returns:
            list[AuditLogs]: list of audit logs
        """
        return self.auditLogsRepository.findByType(type)