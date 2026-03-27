from infrastructure.database.repositories.badgeRepository import BadgeRepository
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
    
    
    def delete(self, badgeId: str) -> None:
        """
        Delete a badge.
        
        Args:
            badgeId: ID of the badge
        """
        self.badgeRepository.softDelete(badgeId)