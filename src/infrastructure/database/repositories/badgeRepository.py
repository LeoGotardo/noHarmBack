from core.errorUtils import excLocation
from infrastructure.database.models.badgeModel import BadgeModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.badge import Badge
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from typing import Optional


class BadgeRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
    def _toEntity(self, model: BadgeModel) -> Badge:
        return Badge(
            id=model.id,
            name=model.name,
            description=model.description,
            milestone=model.milestone,
            icon=model.icon,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
        

    def findById(self, id: str, returnModel: bool = False) -> Badge | BadgeModel:
        """Find a badge by ID
        
        Args:
            id (str): Badge ID
            
        Returns:
            Badge: Badge with his full data
        """
        try:
            badgeModel = self.session.query(BadgeModel).filter(BadgeModel.id == id).first()
            if badgeModel:
                return self._toEntity(badgeModel) if not returnModel else badgeModel
            else:
                raise NoHarmException(statusCode=404, message="Badge not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
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
                items = [self._toEntity(item) for item in items]
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            
            return [ self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def create(self, badge: Badge) -> Badge:
        """Create a badge
        
        Args:
            badge (Badge): badge to create
            
        Returns:
            Badge: Badge with his full data
        """
        try:
            badgeModel = BadgeModel(
                name=badge.name,
                description=badge.description,
                milestone=badge.milestone,
                icon=badge.icon,
                status=badge.status,
                created_at=badge.created_at,
                updated_at=badge.updated_at
            )
            self.session.add(badgeModel)
            self.session.commit()
            return self._toEntity(badgeModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def update(self, badge_id: str, updatedBadge: Badge) -> Badge:
        """Update a badge
        
        Args:
            badge (Badge): badge to update
            
        Returns:
            Badge: Badge with his full data
        """
        try:
            badgeModel = self.findById(badge_id, returnModel=True)
            
            badgeModel.name = updatedBadge.name if updatedBadge.name else badgeModel.name
            badgeModel.description = updatedBadge.description if updatedBadge.description else badgeModel.description
            badgeModel.milestone = updatedBadge.milestone if updatedBadge.milestone else badgeModel.milestone
            badgeModel.icon = updatedBadge.icon if updatedBadge.icon else badgeModel.icon
            badgeModel.status = updatedBadge.status if updatedBadge.status else badgeModel.status
            
            self.session.commit()
            
            return self._toEntity(badgeModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def updateStatus(self, id: str, status: str) -> Badge:
        """Update a badge status
        
        Args:
            id (str): Badge ID
            status (int): New status
            
        Returns:
            Badge: Badge with his full data
        """
        try:
            badgeModel = self.findById(id, returnModel=True)
            badgeModel.status = config.STATUS_CODES[status]
            self.session.commit()
            
            return self._toEntity(badgeModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def delete(self, id: str) -> bool:
        """Delete a badge
        
        Args:
            id (str): Badge ID
            
        Returns:
            bool: True if badge was deleted, False if not
        """
        try:
            badgeModel = self.findById(id, returnModel=True)
            self.session.delete(badgeModel)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a badge

        Args:
            id (str): Badge ID

        Returns:
            bool: True if badge was soft deleted, False if not
        """
        try:
            badgeModel = self.findById(id, returnModel=True)
            badgeModel.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
