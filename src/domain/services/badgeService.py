from infrastructure.database.repositories.badgeRepository import BadgeRepository
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from domain.entities.badge import Badge
from core.database import Database
from typing import Optional, overload


class BadgeService:
    def __init__(self, db):
        self.database: Database = db
        self.badgeRepository = BadgeRepository(self.database)
    
    
    @overload
    def getAll(self, params: None = None) -> list[Badge]: ...
    @overload
    def getAll(self, params: PaginationParams) -> PaginatedResponse[Badge]: ...
    def getAll(self, params: Optional[PaginationParams] = None) -> list[Badge] | PaginatedResponse[Badge]:
        """
        Return all badges, optionally paginated.

        Args:
            params: Optional pagination parameters

        Returns:
            list[Badge] | PaginatedResponse[Badge]
        """
        return self.badgeRepository.findAll(params)
    
    
    def get(self, badgeId: str) -> Badge:
        """
        Return a badge by ID.
        
        Args:
            badgeId: ID of the badge
            
        Returns:
            Badge: badge
        """
        return self.badgeRepository.findById(badgeId)
    
    
    def create(self, newBadge: Badge) -> Badge:
        """
        Create a new badge.
        
        Args:
            newBadge: badge to create
            
        Returns:
            Badge: created badge
        """
        return self.badgeRepository.create(newBadge)
        
    
    def update(self, id: str, newBadge: Badge) -> Badge:
        """
        Edit a badge.
        
        Args:
            newBadge: badge to edit
            
        Returns:
            Badge: updated badge
        """
        return self.badgeRepository.update(id, newBadge)  
    
    
    def updateStatus(self, badgeId: str, status: int) -> Badge:
        """
        Update the status of a badge.

        Args:
            badgeId: ID of the badge
            status: new status code (ex: 1 enabled, 0 disabled)
        """
        return self.badgeRepository.updateStatus(badgeId, status)


    def delete(self, badgeId: str) -> Badge:
        """
        Soft delete a badge.

        Args:
            badgeId: ID of the badge

        Returns:
            Badge: the badge, with status = deleted
        """
        return self.badgeRepository.softDelete(badgeId)

