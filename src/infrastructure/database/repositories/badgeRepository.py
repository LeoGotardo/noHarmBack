from infrastructure.database.models.badgeModel import BadgeModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.badge import Badge
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from typing import Optional

import sys


class BadgeRepository(Badge):
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        

    def findById(self, id: str) -> Badge:
        """Find a badge by ID
        
        Args:
            id (str): Badge ID
            
        Returns:
            Badge: Badge with his full data
        """
        try:
            badge = self.session.query(BadgeModel).filter(BadgeModel.id == id).first()
            if badge:
                return badge
            else:
                raise NoHarmException(status_code=404, message="Badge not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findAll(self, params: Optional[PaginationParams] = None) -> list[Badge] | PaginatedResponse[Badge]:
        """Find all badges, optionally paginated

        Args:
            params: Optional pagination parameters (page, pageSize)

        Returns:
            list[Badge] | PaginatedResponse[Badge]: List of Badges or paginated response
        """
        try:
            query = self.session.query(BadgeModel)
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                items = query.offset(offset).limit(params.pageSize).all()
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            return query.all()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def create(self, badge: Badge) -> Badge:
        """Create a badge
        
        Args:
            badge (Badge): badge to create
            
        Returns:
            Badge: Badge with his full data
        """
        try:
            self.session.add(badge) # TODO: Will be nice to return the badge object that was just created
            self.session.commit()
            return badge
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def update(self, badge_id: str, updatedBadge: Badge) -> Badge:
        """Update a badge
        
        Args:
            badge (Badge): badge to update
            
        Returns:
            Badge: Badge with his full data
        """
        try:
            badge = self.findById(badge_id)
            badge.name = updatedBadge.name if updatedBadge.name else badge.name
            badge.description = updatedBadge.description if updatedBadge.description else badge.description
            badge.milestone = updatedBadge.milestone if updatedBadge.milestone else badge.milestone
            badge.icon = updatedBadge.icon if updatedBadge.icon else badge.icon
            badge.status = updatedBadge.status if updatedBadge.status else badge.status
            self.session.commit()
            return badge
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def updateStatus(self, id: str, status: int) -> Badge:
        """Update a badge status
        
        Args:
            id (str): Badge ID
            status (int): New status
            
        Returns:
            Badge: Badge with his full data
        """
        try:
            badge = self.findById(id)
            badge.status = status
            self.session.commit()
            return badge
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def delete(self, id: str) -> bool:
        """Delete a badge
        
        Args:
            id (str): Badge ID
            
        Returns:
            bool: True if badge was deleted, False if not
        """
        try:
            badge = self.findById(id)
            self.session.delete(badge)
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
            id (str): Badge ID

        Returns:
            bool: True if badge was soft deleted, False if not
        """
        try:
            badge = self.findById(id)
            badge.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
