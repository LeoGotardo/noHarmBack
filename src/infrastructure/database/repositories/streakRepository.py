from domain.entities.streak import Streak

from datetime import datetime

class StreakRepository(Streak):
    def __init__(self, db):
        self.db = db
        
    
    def findByOwnerId(self, owner_id: str) -> Streak:
        """Find a streak by owner ID
        
        Args:
            owner_id (str): Owner ID
            
        Returns:
            Streak: Streak with his full data
        """
        ...
        
    
    def findAllByOwnerId(self, owner_id: str) -> list[Streak]:
        """Find all streaks by owner ID
        
        Args:
            owner_id (str): Owner ID
            
        Returns:
            list[Streak]: List of Streaks
        """
        ...
        
        
    def findCurrentRecord(self, owner_id: str) -> Streak:
        """Find the current streak record by owner ID
        
        Args:
            owner_id (str): Owner ID
            
        Returns:
            Streak: Streak with his full data
        """
        ...
        
    
    def findCurrentStreak(self, owner_id: str) -> Streak:
        """Find the current streak by owner ID
        
        Args:
            owner_id (str): Owner ID
            
        Returns:
            Streak: Streak with his full data
        """
        ...
    
    
    def create(self, Streak: Streak) -> Streak:
        """Create a streak
        
        Args:
            Streak (Streak): Streak to create
            
        Returns:
            Streak: Streak with his full data
        """
        ...
        
    
    def update(self, Streak: Streak) -> Streak:
        """Update a streak
        
        Args:
            Streak (Streak): Streak to update
            
        Returns:
            Streak: Streak with his full data
        """
        ...
        
        
    def markAsRecord(self, id: str) -> Streak:
        """Mark a streak as record
        
        Args:
            id (str): Streak ID
            
        Returns:
            Streak: Streak with his full data
        """
        ...
        
        
    def updateStart(self, id: str, start: datetime) -> Streak:
        """Update a streak start
        
        Args:
            id (str): Streak ID
            start (datetime): New start
            
        Returns:
            Streak: Streak with his full data
        """
        ...
        
    
    def updateEnd(self, id: str, end: datetime) -> Streak:
        """Update a streak end
        
        Args:
            id (str): Streak ID
            end (datetime): New end
            
        Returns:
            Streak: Streak with his full data
        """
        ...
        
    
    def updateStatus(self, id: str, status: int) -> Streak:
        """Update a streak status
        
        Args:
            id (str): Streak ID
            status (int): New status
            
        Returns:
            Streak: Streak with his full data
        """
        ...
        
    
    def delete(self, id: str) -> bool:
        """Delete a streak
        
        Args:
            id (str): Streak ID
            
        Returns:
            bool: True if streak was deleted, False if not
        """
        ...
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a streak
        
        Args:
            id (str): Streak ID
            
        Returns:
            bool: True if streak was soft deleted, False if not
        """
        ...