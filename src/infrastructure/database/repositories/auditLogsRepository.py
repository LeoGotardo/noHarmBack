from domain.entities.user import User
from domain.entities.auditLogs import AuditLogs


from datetime import datetime


class AuditLogsRepository(User):
    def __init__(self, db):
        self.db = db
        
    
    def findById(self, id: str) -> AuditLogs:
        """Find an audit log by ID
        
        Args:
            id (str): AuditLogs ID
            
        Returns:
            AuditLogs: AuditLogs with his full data
        """
        ...
        
        
    def findByType(self, type: int) -> list[AuditLogs]:
        """Find all audit logs by type
        
        Args:
            type (int): AuditLogs type
            
        Returns:
            list[AuditLogs]: List of AuditLogs
        """
        ...
        
    
    def findByCatalystId(self, catalyst_id: int) -> list[AuditLogs]:
        """Find all audit logs by catalyst ID
        
        Args:
            catalyst_id (str): Catalyst ID
            
        Returns:
            list[AuditLogs]: List of AuditLogs
        """
        ...
        
    
    def findByDateRange(self, start: datetime, end: datetime) -> list[AuditLogs]:
        """Find all audit logs by date range
        
        Args:
            start (datetime): Start date
            end (datetime): End date
            
        Returns:
            list[AuditLogs]: List of AuditLogs
        """
        ...
        
        
    def create(self, AuditLogs: AuditLogs) -> AuditLogs:
        """Create an audit log
        
        Args:
            AuditLogs (AuditLogs): AuditLogs to create
            
        Returns:
            AuditLogs: AuditLogs with his full data
        """
        ...