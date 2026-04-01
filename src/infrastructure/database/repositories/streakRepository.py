from infrastructure.database.models.streakModel import StreakModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.streak import Streak
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from datetime import datetime

import sys


class StreakRepository(Streak):
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
        
    def findById(self, id: str) -> Streak:
        """Find a streak by ID
        
        Args:
            id (str): Streak ID
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streak = self.session.query(StreakModel).filter(StreakModel.id == id).first()
            if streak:
                return streak
            else:
                raise NoHarmException(status_code=404, message="Streak not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
    
    
    def findAllByOwnerId(self, owner_id: str) -> list[Streak]:
        """Find all streaks by owner ID
        
        Args:
            owner_id (str): Owner ID
            
        Returns:
            list[Streak]: List of Streaks
        """
        try:
            streaks = self.session.query(StreakModel).filter(StreakModel.owner_id == owner_id).all()
            return streaks
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def findCurrentRecord(self, owner_id: str) -> Streak:
        """Find the current streak record by owner ID
        
        Args:
            owner_id (str): Owner ID
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streak = self.session.query(StreakModel).filter(StreakModel.owner_id == owner_id, StreakModel.is_record == True).first()
            if streak:
                return streak
            else:
                raise NoHarmException(status_code=404, message="Streak not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
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
                raise NoHarmException(status_code=404, message="Streak not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
    
    
    def create(self, Streak: Streak) -> Streak:
        """Create a streak
        
        Args:
            Streak (Streak): Streak to create
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            self.session.add(Streak)
            self.session.commit()
            return Streak
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
        
    
    def update(self, streak_id: str, updatedStreak: Streak) -> Streak:
        """Update a streak
        
        Args:
            Streak (Streak): Streak to update
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streak = self.findById(streak_id)
            streak.start = updatedStreak.start if updatedStreak.start else streak.start
            streak.end = updatedStreak.end if updatedStreak.end else streak.end
            streak.status = updatedStreak.status if updatedStreak.status else streak.status
            self.session.commit()
            return streak
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def markAsRecord(self, id: str) -> Streak:
        """Mark a streak as record
        
        Args:
            id (str): Streak ID
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streak = self.findById(id)
            streak.is_record = True
            self.session.commit()
            return streak
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
    
    
    def updateEnd(self, id: str, end: datetime) -> Streak:
        """Update a streak end
        
        Args:
            id (str): Streak ID
            end (datetime): New end
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streak = self.findById(id)
            streak.end = end
            self.session.commit()
            return streak
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def updateStatus(self, id: str, status: int) -> Streak:
        """Update a streak status
        
        Args:
            id (str): Streak ID
            status (int): New status
            
        Returns:
            Streak: Streak with his full data
        """
        try:
            streak = self.findById(id)
            streak.status = status
            self.session.commit()
            return streak
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def delete(self, id: str) -> bool:
        """Delete a streak
        
        Args:
            id (str): Streak ID
            
        Returns:
            bool: True if streak was deleted, False if not
        """
        try:
            streak = self.findById(id)
            self.session.delete(streak)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a streak

        Args:
            id (str): Streak ID

        Returns:
            bool: True if streak was soft deleted, False if not
        """
        try:
            streak = self.findById(id)
            streak.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findAllByOwnerIdPaginated(self, owner_id: str, params: PaginationParams) -> PaginatedResponse[Streak]:
        """Find all streaks by owner ID with pagination

        Args:
            owner_id: Owner user ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[Streak]: Paginated list of streaks
        """
        try:
            query = self.session.query(StreakModel).filter(StreakModel.owner_id == owner_id)
            total = query.count()
            offset = (params.page - 1) * params.pageSize
            items = query.offset(offset).limit(params.pageSize).all()
            return createPaginatedResponse(items, total, params.page, params.pageSize)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')