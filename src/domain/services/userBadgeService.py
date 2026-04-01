from infrastructure.database.repositories.userBadgesRepository import UserBadgesRepository
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from domain.entities.userBadge import UserBadge
from core.database import Database


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
    
    
    def findByUserId(self, user_id: str) -> list[UserBadge]:
        """Find all badges by user ID
        
        Args:
            user_id (str): User ID
            
        Returns:
            list[UserBadge]: List of UserBadges
        """
        return self.userBadgeRepository.findByUserId(user_id)
    
    
    def findByBadgeId(self, badge_id: str) -> list[UserBadge]:
        """Find all badges by badge ID
        
        Args:
            badge_id (str): Badge ID
            
        Returns:
            list[UserBadge]: List of UserBadges
        """
        return self.userBadgeRepository.findByBadgeId(badge_id)
    
    
    def existsByUserAndBadge(self, user_id: str, badge_id: str) -> bool:
        """Check if a badge exists by user ID and badge ID
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID
            
        Returns:
            bool: True if badge exists, False if not
        """
        return self.userBadgeRepository.existsByUserAndBadge(user_id, badge_id)
    
    
    def grant(self, user_id: str, badge_id: str, given_at: str) -> bool:
        """Grant a badge to a user
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID
            given_at (str): Date of creation
            
        Returns:
            bool: True if badge was granted, False if not
        """
        return self.userBadgeRepository.grant(user_id, badge_id, given_at)
    
    
    def revoke(self, user_id: str, badge_id: str) -> bool:
        """Revoke a badge from a user
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID    
            
        Returns:
            bool: True if badge was revoked, False if not
        """
        return self.userBadgeRepository.revoke(user_id, badge_id)
    
    
    def updateStatus(self, id: str, status: int) -> UserBadge:
        """Update a badge status
        
        Args:
            id (str): UserBadge ID
            status (int): New status
            
        Returns:
            UserBadge: UserBadge with his full data
        """
        return self.userBadgeRepository.updateStatus(id, status)
    
    
    def delete(self, id: str) -> bool:
        """Soft delete a badge
        
        Args:
            id (str): UserBadge ID
            
        Returns:
            bool: True if badge was deleted, False if not
        """
        return self.userBadgeRepository.softDelete(id)
    
    
    def getByUserIdPaginated(self, user_id: str, params: PaginationParams) -> PaginatedResponse[UserBadge]:
        """List all badges from a user with pagination

        Args:
            user_id: User ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[UserBadge]: Paginated list of user badges
        """
        return self.userBadgeRepository.findByUserIdPaginated(user_id, params)
    
    
    def getByBadgeIdPaginated(self, badge_id: str, params: PaginationParams) -> PaginatedResponse[UserBadge]:
        """List all user badges by badge ID with pagination

        Args:
            badge_id: Badge ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[UserBadge]: Paginated list of user badges
        """
        return self.userBadgeRepository.findByBadgeIdPaginated(badge_id, params)