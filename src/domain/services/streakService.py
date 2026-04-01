from infrastructure.database.repositories.streakRepository import StreakRepository
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from domain.entities.streak import Streak
from core.database import Database

from datetime import datetime


class StreakService:
    def __init__(self, db):
        self.database: Database = db
        self.streakRepository = StreakRepository(self.database)
        
        
    def get(self, streakId: str) -> Streak:
        """
        Return a streak by ID.
        
        Args:
            streakId: ID of the streak
            
        Returns:
            Streak: Streak with his full data
        """
        return self.streakRepository.findById(streakId)
    
    
    def getAllByUserId(self, userId: str) -> list[Streak]:
        """
        Return all streaks by user ID.
        
        Args:
            userId: ID of the user
            
        Returns:
            list[Streak]: list of streaks
        """
        return self.streakRepository.findAllByOwnerId(userId)
    
    
    def getCurrentByUserId(self, userId: str) -> Streak:
        """
        Return the current streak by user ID.
        
        Args:
            userId: ID of the user
            
        Returns:
            Streak: current streak
        """
        return self.streakRepository.findCurrentStreak(userId)
    
    
    def getRecordByUserId(self, userId: str) -> Streak:
        """
        Return the record streak by user ID.
        
        Args:
            userId: ID of the user
            
        Returns:
            Streak: record streak
        """
        return self.streakRepository.findCurrentRecord(userId)


    def getAllByUserIdPaginated(self, userId: str, params: PaginationParams) -> PaginatedResponse[Streak]:
        """
        Return paginated streaks by user ID.

        Args:
            userId: ID of the user
            params: Pagination parameters

        Returns:
            PaginatedResponse[Streak]: Paginated list of streaks
        """
        return self.streakRepository.findAllByOwnerIdPaginated(userId, params)


    
    def markAsRecord(self, streakId: str) -> Streak:
        """
        Mark a streak as record.
        
        Args:
            streakId: ID of the streak
            
        Returns:
            Streak: streak with its full data
        """
        return self.streakRepository.markAsRecord(streakId)
    
    
    def create(self, newStreak: Streak) -> Streak:
        """
        Create a streak.
        
        Args:
            newStreak: streak to create
            
        Returns:
            Streak: created streak
        """
        return self.streakRepository.create(newStreak)
    
    
    def updateStatus(self, streakId: str, status: int) -> None:
        """
        Update the status of a streak.
        
        Args:
            streakId: ID of the streak
            status: new status (ex: 1 enabled, 0 disabled)
        """
        self.streakRepository.updateStatus(streakId, status)
        
        
    def updateEndedAt(self, streakId: str, endedAt: datetime) -> None:
        """
        Update the endedAt field of a streak.
        
        Args:
            streakId: ID of the streak
            endedAt: new endedAt value
        """
        self.streakRepository.updateEndedAt(streakId, endedAt)
        
        
    def delete(self, streakId: str) -> bool:
        """
        Soft delete a streak.
        
        Args:
            streakId: ID of the streak
            
        Returns:
            bool: True if streak was deleted, False if not
        """
        return self.streakRepository.softDelete(streakId)