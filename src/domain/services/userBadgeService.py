from infrastructure.database.repositories.userBadgesRepository import UserBadgesRepository
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from domain.entities.userBadge import UserBadge
from core.database import Database
from typing import Optional, overload
from datetime import datetime


class UserBadgeService:
    def __init__(self, db):
        self.database: Database = db
        self.userBadgeRepository = UserBadgesRepository(self.database)
        
    
    def findById(self, id: str) -> UserBadge:
        """Find by UserBadge ID
        
        Args:
            id (str): UserBadge ID
            
        Returns:
            UserBadge: UserBadge with his full data
        """
        return self.userBadgeRepository.findById(id)
    
    
    @overload
    def findByUserId(self, user_id: str, params: None = None) -> list[UserBadge]: ...
    @overload
    def findByUserId(self, user_id: str, params: PaginationParams) -> PaginatedResponse[UserBadge]: ...
    def findByUserId(self, user_id: str, params: Optional[PaginationParams] = None) -> list[UserBadge] | PaginatedResponse[UserBadge]:
        """Find all badges by user ID, optionally paginated

        Args:
            user_id (str): User ID
            params: Optional pagination parameters

        Returns:
            list[UserBadge] | PaginatedResponse[UserBadge]
        """
        return self.userBadgeRepository.findByUserId(user_id, params)
    
    
    @overload
    def findByBadgeId(self, badge_id: str, params: None = None) -> list[UserBadge]: ...
    @overload
    def findByBadgeId(self, badge_id: str, params: PaginationParams) -> PaginatedResponse[UserBadge]: ...
    def findByBadgeId(self, badge_id: str, params: Optional[PaginationParams] = None) -> list[UserBadge] | PaginatedResponse[UserBadge]:
        """Find all badges by badge ID, optionally paginated

        Args:
            badge_id (str): Badge ID
            params: Optional pagination parameters

        Returns:
            list[UserBadge] | PaginatedResponse[UserBadge]
        """
        return self.userBadgeRepository.findByBadgeId(badge_id, params)
    
    
    def existsByUserAndBadge(self, user_id: str, badge_id: str) -> bool:
        """Check if a badge exists by user ID and badge ID
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID
            
        Returns:
            bool: True if badge exists, False if not
        """
        return self.userBadgeRepository.existsByUserAndBadge(user_id, badge_id)
    
    
    def grant(self, user_id: str, badge_id: str, given_at: datetime | None = None) -> UserBadge:
        """Grant a badge to a user

        Args:
            user_id (str): User ID
            badge_id (str): Badge ID
            given_at (datetime): When the badge was earned; defaults to now

        Returns:
            UserBadge: The granted user badge
        """
        return self.userBadgeRepository.grant(user_id, badge_id, given_at)


    def revoke(self, user_id: str, badge_id: str) -> UserBadge:
        """Revoke a badge from a user

        Args:
            user_id (str): User ID
            badge_id (str): Badge ID

        Returns:
            UserBadge: The revoked user badge
        """
        return self.userBadgeRepository.revoke(user_id, badge_id)
    
    
    def update(self, id: str, updatedUserBadge: UserBadge) -> UserBadge:
        """Update a badge
        
        Args:
            id (str): UserBadge ID
            updatedUserBadge (UserBadge): UserBadge with updated data
            
        Returns:
            UserBadge: UserBadge with his full data
        """
        return self.userBadgeRepository.update(id, updatedUserBadge)
    
    
    def updateStatus(self, id: str, status: int) -> UserBadge:
        """Update a badge status

        Args:
            id (str): UserBadge ID
            status (int): New status code

        Returns:
            UserBadge: UserBadge with his full data
        """
        return self.userBadgeRepository.updateStatus(id, status)


    def delete(self, id: str) -> UserBadge:
        """Soft delete a badge

        Args:
            id (str): UserBadge ID

        Returns:
            UserBadge: The soft-deleted user badge
        """
        return self.userBadgeRepository.softDelete(id)
    
    