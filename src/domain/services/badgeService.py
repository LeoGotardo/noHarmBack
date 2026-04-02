from infrastructure.database.repositories.badgeRepository import BadgeRepository
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from domain.entities.badge import Badge
from core.database import Database
from typing import Optional


class BadgeService:
    def __init__(self, db):
        self.database: Database = db
        self.badgeRepository = BadgeRepository(self.database)
    
    
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
        
