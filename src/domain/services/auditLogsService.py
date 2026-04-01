from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from domain.entities.auditLogs import AuditLogs
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
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


    def getAllPaginated(self, params: PaginationParams) -> PaginatedResponse[AuditLogs]:
        """
        Return paginated audit logs.

        Args:
            params: Pagination parameters (page, pageSize)

        Returns:
            PaginatedResponse[AuditLogs]: Paginated list of audit logs
        """
        return self.auditLogsRepository.findAllPaginated(params)


    def getByTypePaginated(self, type: int, params: PaginationParams) -> PaginatedResponse[AuditLogs]:
        """
        Return paginated audit logs filtered by type.

        Args:
            type: Type of the audit log
            params: Pagination parameters

        Returns:
            PaginatedResponse[AuditLogs]: Paginated list of audit logs
        """
        return self.auditLogsRepository.findByTypePaginated(type, params)


    def getByCatalystPaginated(self, catalistId: str, params: PaginationParams) -> PaginatedResponse[AuditLogs]:
        """
        Return paginated audit logs filtered by catalyst.

        Args:
            catalistId: ID of the catalyst
            params: Pagination parameters

        Returns:
            PaginatedResponse[AuditLogs]: Paginated list of audit logs
        """
        return self.auditLogsRepository.findByCatalystIdPaginated(catalistId, params)


    def getByDateRangePaginated(
        self,
        startDate: str,
        endDate: str,
        params: PaginationParams
    ) -> PaginatedResponse[AuditLogs]:
        """
        Return paginated audit logs filtered by date range.

        Args:
            startDate: Start date (YYYY-MM-DD)
            endDate: End date (YYYY-MM-DD)
            params: Pagination parameters

        Returns:
            PaginatedResponse[AuditLogs]: Paginated list of audit logs
        """
        from datetime import datetime
        start = datetime.strptime(startDate, "%Y-%m-%d")
        end = datetime.strptime(endDate, "%Y-%m-%d")
        return self.auditLogsRepository.findByDateRangePaginated(start, end, params)