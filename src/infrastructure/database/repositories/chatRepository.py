from domain.entities.chat import Chat

from datetime import datetime

class ChatRepository(Chat):
    def __init__(self, db):
        self.db = db
        
        
    def findById(self, id: str) -> Chat:
        """Find a chat by ID
        
        Args:
            id (str): Chat ID
            
        Returns:
            Chat: Chat with his full data
        """
        ...
        
    
    def findByParticipants(self, participant_id: str) -> list[Chat]:
        """Find all chats by participant ID
        
        Args:
            participant_id (str): Participant ID
            
        Returns:
            list[Chat]: List of Chats
        """
        ...
        
    
    def findAllByUserId(self, user_id: str) -> list[Chat]:
        """Find all chats by user ID
        
        Args:
            user_id (str): User ID
            
        Returns:
            list[Chat]: List of Chats
        """
        ...
        
        
    def create(self, Chat: Chat) -> Chat:
        """Create a chat
        
        Args:
            Chat (Chat): Chat to create
            
        Returns:
            Chat: Chat with his full data
        """
        ...
        
        
    def updateStatus(self, id: str, status: int) -> Chat:
        """Update a chat status
        
        Args:
            id (str): Chat ID
            status (int): New status
            
        Returns:
            Chat: Chat with his full data
        """
        ...
        
        
    def updateEndedAt(self, id: str, ended_at: datetime) -> Chat:
        """Update a chat ended at
        
        Args:
            id (str): Chat ID
            ended_at (datetime): New ended at
            
        Returns:
            Chat: Chat with his full data
        """
        ...
        
        
    def delete(self, id: str) -> bool:
        """Delete a chat
        
        Args:
            id (str): Chat ID
            
        Returns:
            bool: True if chat was deleted, False if not
        """
        ...
        
        
    def softDelete(self, id: str) -> bool:
        """Soft delete a chat
        
        Args:
            id (str): Chat ID
            
        Returns:
            bool: True if chat was soft deleted, False if not
        """
        ...