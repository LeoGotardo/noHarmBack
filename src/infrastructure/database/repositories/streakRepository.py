from core.errorUtils import excLocation
from infrastructure.database.models.streakModel import StreakModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.streak import Streak
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from datetime import datetime

from typing import Optional

import sys


class StreakRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
        
    def _toEntity(self, model: StreakModel) -> Streak:
        return Streak(
            id=model.id,
            owner_id=model.owner_id,
            start=model.start,
            status=model.status,
            is_record=model.is_record,
            end=model.end,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
        
        
    def findById(self, id: str, returnModel: bool = False) -> Streak | StreakModel:
        """Find a streak by ID
        
        Args:
            id (str): Streak ID
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streak = self.session.query(StreakModel).filter(StreakModel.id == id).first()
            if streak:
                return streak if returnModel else self._toEntity(streak)
            else:
                raise NoHarmException(statusCode=404, message="Streak not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
    
    def findAllByOwnerId(self, owner_id: str, params: Optional[PaginationParams] = None) -> list[Streak] | PaginatedResponse[Streak]:
        """Find all streaks by owner ID, optionally paginated

        Args:
            owner_id (str): Owner ID
            params: Optional pagination parameters

        Returns:
            list[Streak] | PaginatedResponse[Streak]
        """
        try:
            query = self.session.query(StreakModel).filter(StreakModel.owner_id == owner_id)
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                
                items = query.offset(offset).limit(params.pageSize).all()
                items = [self._toEntity(item) for item in items]
                
                return createPaginatedResponse(items, total, params.page, params.pageSize)  
            
            return [self._toEntity(items) for items in query.all()]  
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def findCurrentRecord(self, owner_id: str) -> Streak:
        """Find the current streak record by owner ID
        
        Args:
            owner_id (str): Owner ID
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streakModel = self.session.query(StreakModel).filter(StreakModel.owner_id == owner_id, StreakModel.is_record == True).first()
            if streakModel:
                return self._toEntity(streakModel)
            else:
                raise NoHarmException(statusCode=404, message="Streak not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def findCurrentStreak(self, owner_id: str) -> Streak:
        """Find the current streak by owner ID
        
        Args:
            owner_id (str): Owner ID
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streak = self.session.query(StreakModel).filter(StreakModel.owner_id == owner_id, StreakModel.status == config.STATUS_CODES["enabled"]).first()
            if streak:
                return streak  
            else:
                raise NoHarmException(statusCode=404, message="Streak not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
    
    def create(self, Streak: Streak) -> Streak:
        """Create a streak
        
        Args:
            Streak (Streak): Streak to create
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streakModel = StreakModel(
                owner_id=Streak.owner_id,
                start=Streak.start,
                status=Streak.status,
                is_record=Streak.is_record,
                end=Streak.end,
                created_at=Streak.created_at,
                updated_at=Streak.updated_at
            )
            
            self.session.add(streakModel)
            self.session.commit()
            
            return self._toEntity(streakModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def update(self, streak_id: str, updatedStreak: Streak) -> Streak:
        """Update a streak
        
        Args:
            Streak (Streak): Streak to update
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streakModel = self.findById(streak_id, returnModel=True)
            
            streakModel.start = updatedStreak.start if updatedStreak.start else streakModel.start
            streakModel.end = updatedStreak.end if updatedStreak.end else streakModel.end
            streakModel.status = updatedStreak.status if updatedStreak.status else streakModel.status
            
            self.session.commit()
            
            return self._toEntity(streakModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def markAsRecord(self, id: str) -> Streak:
        """Mark a streak as record
        
        Args:
            id (str): Streak ID
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streakModel = self.findById(id, returnModel=True)
            
            streakModel.is_record = True
            
            self.session.commit()
            
            return self._toEntity(streakModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
    
    def updateEnd(self, id: str, end: datetime) -> Streak:
        """Update a streak end
        
        Args:
            id (str): Streak ID
            end (datetime): New end
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streakModel = self.findById(id, returnModel=True)
            
            streakModel.end = end  
            
            self.session.commit()
            
            return self._toEntity(streakModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def updateStatus(self, id: str, status: int) -> Streak:
        """Update a streak status
        
        Args:
            id (str): Streak ID
            status (int): New status
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streakModel = self.findById(id, returnModel=True)
            
            streakModel.status = status
            
            self.session.commit()
            
            return self._toEntity(streakModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def delete(self, id: str) -> bool:
        """Delete a streak
        
        Args:
            id (str): Streak ID
            
        Returns:
            bool: True if streak was deleted, False if not
        """
        try:
            streakModel = self.findById(id, returnModel=True)
            
            self.session.delete(streakModel)
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a streak

        Args:
            id (str): Streak ID

        Returns:
            bool: True if streak was soft deleted, False if not
        """
        try:
            streakModel = self.findById(id, returnModel=True)
            
            streakModel.status = config.STATUS_CODES["deleted"]
            
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

