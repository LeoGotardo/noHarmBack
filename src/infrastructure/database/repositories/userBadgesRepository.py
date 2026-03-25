from infrastructure.database.models.userBedgesModel import UserBadgesModel
from domain.entities.userBadge import UserBadge

from core.database import Database

from datetime import datetime

class UserBadgesRepository(UserBadge):
    def __init__(self, database: Database):
        self.session = database.session
        
    
    def findByUserId(self, user_id: str) -> list[UserBadge]:
        """Find all badges by user ID
        
        Args:
            user_id (str): User ID
            
        Returns:
            list[UserBadge]: List of UserBadges
        """
        ...
        
    
    def findByBadgeId(self, badge_id: str) -> list[UserBadge]:
        """Find all badges by badge ID
        
        Args:
            badge_id (str): Badge ID
            
        Returns:
            list[UserBadge]: List of UserBadges
        """
        ...
        
    
    def existsByUserAndBadge(self, user_id: str, badge_id: str) -> bool:
        """Check if a badge exists by user ID and badge ID
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID
            
        Returns:
            bool: True if badge exists, False if not
        """
        ...
        
        
    def grant(self, user_id: str, badge_id: str, given_at: datetime) -> bool:
        """Grant a badge to a user
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID
            given_at (datetime): Date of creation
            
        Returns:
            bool: True if badge was granted, False if not
        """
        ...
        
    
    def revoke(self, user_id: str, badge_id: str) -> bool:
        """Revoke a badge from a user
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID    
            
        Returns:
            bool: True if badge was revoked, False if not
        """
        ...
        
    
    def listAll(self) -> list[UserBadge]:
        """List all badges
        
        Returns:
            list[UserBadge]: List of UserBadges
        """
        ...
        
        
    def updateStatus(self, id: str, status: int) -> UserBadge:
        """Update a badge status
        
        Args:
            id (str): UserBadge ID
            status (int): New status
            
        Returns:
            UserBadge: UserBadge with his full data
        """
        ...
        
    
    def delete(self, id: str) -> bool:
        """Delete a badge
        
        Args:
            id (str): UserBadge ID
            
        Returns:
            bool: True if badge was deleted, False if not
        """
        ...
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a badge
        
        Args:
            id (str): UserBadge ID
            
        Returns:
            bool: True if badge was soft deleted, False if not
        """
        ...