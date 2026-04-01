from infrastructure.database.repositories.badgeRepository import BadgeRepository
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from domain.entities.badge import Badge
from core.database import Database


class BadgeService:
    def __init__(self, db):
        self.database: Database = db
        self.badgeRepository = BadgeRepository(self.database)
    
    
    def getAll(self) -> list[Badge]:
        """
        Return all badges.
        
        Returns:
            list[Badge]: list of badges
        """
        return self.badgeRepository.findAll()
    
    
    def get(self, badgeId: str) -> Badge:
        """
        Return a badge by ID.
        
        Args:
            badgeId: ID of the badge
            
        Returns:
            Badge: badge
        """
        return self.badgeRepository.findById(badgeId)
        
    
    def update(self, newBadge: Badge) -> Badge:
        """
        Edit a badge.
        
        Args:
            newBadge: badge to edit
            
        Returns:
            Badge: updated badge
        """
        return self.badgeRepository.update(newBadge)
    
    
    def updateStatus(self, badgeId: str, status: int) -> None:
        """
        Update the status of a badge.
        
        Args:
            badgeId: ID of the badge
            status: new status (ex: 1 enabled, 0 disabled)
        """
        return self.badgeRepository.updateStatus(badgeId, status)
    
    
    def delete(self, badgeId: str) -> None:
        """
        Delete a badge.
        
        Args:
            badgeId: ID of the badge
        """
        self.badgeRepository.softDelete(badgeId)
        
        
    def getAllPaginated(self, params: PaginationParams) -> PaginatedResponse[Badge]:
        """
        Return paginated badges.

        Args:
            params: Pagination parameters (page, pageSize)

        Returns:
            PaginatedResponse[Badge]: Paginated list of badges
        """
        return self.badgeRepository.findAllPaginated(params)