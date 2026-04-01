from infrastructure.database.models.userBedgesModel import UserBadgesModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.userBadge import UserBadge
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from datetime import datetime

import sys

class UserBadgesRepository(UserBadge):
    def __init__(self, database: Database):
        self.database = database
        self.session = self.database.session
        self.engine = self.database.engine
        
    
    def findById(self, id: str) -> UserBadge:
        """Find a badge by ID
        
        Args:
            id (str): UserBadge ID
            
        Returns:
            UserBadge: UserBadge with his full data
        """
        try:
            userBadge = self.session.query(UserBadgesModel).filter(UserBadgesModel.id == id).first()
            if userBadge:
                return userBadge
            else:
                raise NoHarmException(status_code=404, message="UserBadge not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findByUserId(self, user_id: str) -> list[UserBadge]:
        """Find all badges by user ID
        
        Args:
            user_id (str): User ID
            
        Returns:
            list[UserBadge]: List of UserBadges
        """
        try:
            userBadges = self.session.query(UserBadgesModel).filter(UserBadgesModel.user_id == user_id).all()
            return userBadges
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findByBadgeId(self, badge_id: str) -> list[UserBadge]:
        """Find all badges by badge ID
        
        Args:
            badge_id (str): Badge ID
            
        Returns:
            list[UserBadge]: List of UserBadges
        """
        try:
            userBadges = self.session.query(UserBadgesModel).filter(UserBadgesModel.badge_id == badge_id).all()
            return userBadges
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def existsByUserAndBadge(self, user_id: str, badge_id: str) -> bool:
        """Check if a badge exists by user ID and badge ID
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID
            
        Returns:
            bool: True if badge exists, False if not
        """
        try:
            userBadge = self.session.query(UserBadgesModel).filter(UserBadgesModel.user_id == user_id, UserBadgesModel.badge_id == badge_id).first()
            if userBadge:
                return True
            else:
                return False
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def grant(self, user_id: str, badge_id: str, given_at: datetime) -> bool:
        """Grant a badge to a user
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID
            given_at (datetime): Date of creation
            
        Returns:
            bool: True if badge was granted, False if not
        """
        try:
            userBadge = self.session.query(UserBadgesModel).filter(UserBadgesModel.user_id == user_id, UserBadgesModel.badge_id == badge_id).first()
            if userBadge:
                userBadge.given_at = given_at
                self.session.commit()
                return True
            else:
                self.session.add(UserBadgesModel(user_id=user_id, badge_id=badge_id, given_at=given_at))
                self.session.commit()
                return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def revoke(self, user_id: str, badge_id: str) -> bool:
        """Revoke a badge from a user
        
        Args:
            user_id (str): User ID
            badge_id (str): Badge ID    
            
        Returns:
            bool: True if badge was revoked, False if not
        """
        try:
            userBadge = self.session.query(UserBadgesModel).filter(UserBadgesModel.user_id == user_id, UserBadgesModel.badge_id == badge_id).first()
            if userBadge:
                userBadge.status = config.STATUS_CODES["deleted"]
                self.session.commit()
                return True
            else:
                return False
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def updateStatus(self, id: str, status: int) -> UserBadge:
        """Update a badge status
        
        Args:
            id (str): UserBadge ID
            status (int): New status
            
        Returns:
            UserBadge: UserBadge with his full data
        """
        try:
            userBadge = self.findById(id)
            userBadge.status = status
            self.session.commit()
            return userBadge
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
    
    
    def update(self, id: str, updatedUserBadge: UserBadge) -> UserBadge:
        """Update a user badge

        Args:
            id (str): UserBadge ID
            updatedUserBadge (UserBadge): UserBadge with updated data

        Returns:
            UserBadge: UserBadge with his full data
        """
        try:
            userBadge = self.findById(id)
            
            userBadge.status = updatedUserBadge.status if updatedUserBadge.status else userBadge.status
            self.session.commit()
            return userBadge
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
    
    
    def delete(self, id: str) -> bool:
        """Delete a badge
        
        Args:
            id (str): UserBadge ID
            
        Returns:
            bool: True if badge was deleted, False if not
        """
        try:
            userBadge = self.findById(id)
            self.session.delete(userBadge)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def softDelete(self, id: str) -> bool:
        """Soft delete a badge

        Args:
            id (str): UserBadge ID

        Returns:
            bool: True if badge was soft deleted, False if not
        """
        try:
            userBadge = self.findById(id)
            userBadge.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findByUserIdPaginated(self, user_id: str, params: PaginationParams) -> PaginatedResponse[UserBadge]:
        """Find all badges by user ID with pagination

        Args:
            user_id: User ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[UserBadge]: Paginated list of user badges
        """
        try:
            query = self.session.query(UserBadgesModel).filter(UserBadgesModel.user_id == user_id)
            total = query.count()
            offset = (params.page - 1) * params.pageSize
            items = query.offset(offset).limit(params.pageSize).all()
            return createPaginatedResponse(items, total, params.page, params.pageSize)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findByBadgeIdPaginated(self, badge_id: str, params: PaginationParams) -> PaginatedResponse[UserBadge]:
        """Find all user badges by badge ID with pagination

        Args:
            badge_id: Badge ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[UserBadge]: Paginated list of user badges
        """
        try:
            query = self.session.query(UserBadgesModel).filter(UserBadgesModel.badge_id == badge_id)
            total = query.count()
            offset = (params.page - 1) * params.pageSize
            items = query.offset(offset).limit(params.pageSize).all()
            return createPaginatedResponse(items, total, params.page, params.pageSize)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')