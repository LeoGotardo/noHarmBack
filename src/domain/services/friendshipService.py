from infrastructure.database.repositories.friendshipRepository import FriendshipRepository
from domain.entities.friendship import Friendship
from core.database import Database
from core.config import config


class FriendshipService:
    def __init__(self, db):
        self.database: Database = db
        self.friendshipRepository = FriendshipRepository(self.database)
        
        
    def get(self, friendshipId: str) -> Friendship:
        """
        Return a friendship by ID.
        
        Args:
            friendshipId: ID of the friendship
            
        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.findById(friendshipId)
    
    
    def create(self, newFriendship: Friendship) -> Friendship:
        """
        Create a friendship.
        
        Args:
            newFriendship: friendship to create
            
        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.create(newFriendship)
    
    
    def accept(self, friendshipId: str) -> Friendship:
        """
        Accept a friendship.
        
        Args:
            friendshipId: ID of the friendship
            
        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.updateStatus(friendshipId, config.STATUS_CODES["accepted"])
    
    
    def reject(self, friendshipId: str) -> Friendship:
        """
        Reject a friendship.
        
        Args:
            friendshipId: ID of the friendship
            
        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.updateStatus(friendshipId, config.STATUS_CODES["rejected"])
    
    
    def block(self, friendshipId: str) -> Friendship:
        """
        Block a friendship.
        
        Args:
            friendshipId: ID of the friendship
            
        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.updateStatus(friendshipId, config.STATUS_CODES["blocked"])
    
    
    def update(self, friendshipId: str, updatedFriendship: Friendship) -> Friendship:
        """
        Update a friendship.
        
        Args:
            friendshipId: ID of the friendship
            updatedFriendship: Friendship with updated data
            
        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.update(friendshipId, updatedFriendship)
    
    
    def updateStatus(self, id: str, status: str) -> Friendship:
        """
        Update the status of a friendship.
        
        Args:
            id: ID of the friendship
            status: New status (ex: enabled, disabled)
            
        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.updateStatus(id, status)
    
    
    def delete(self, id: str) -> bool:
        """
        Soft delete a friendship.
        
        Args:
            id: ID of the friendship
            
        Returns:
            bool: True if friendship was deleted, False if not
        """
        return self.friendshipRepository.softDelete(id)