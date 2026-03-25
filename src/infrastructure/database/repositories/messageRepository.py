from domain.entities.message import Message

class MessageRepository(Message):
    def __init__(self, db):
        self.db = db
        
    
    def findById(self, id: str) -> Message:
        """Find a message by ID
        
        Args:
            id (str): Message ID
            
        Returns:
            Message: Message with his full data
        """
        ...
        
    
    def findByChatId(self, chat_id: str) -> list[Message]:
        """Find all messages by chat ID
        
        Args:
            chat_id (str): Chat ID
            
        Returns:
            list[Message]: List of Messages
        """
        ...
        
    
    def findUnreadByChatId(self, chat_id: str) -> list[Message]:
        """Find all unread messages by chat ID
        
        Args:
            chat_id (str): Chat ID
            
        Returns:
            list[Message]: List of Messages
        """
        ...
        
    
    def create(self, Message: Message) -> Message:
        """Create a message
        
        Args:
            Message (Message): Message to create
            
        Returns:
            Message: Message with his full data
        """
        ...
        
        
    def markAsRead(self, id: str) -> Message:
        """Mark a message as read
        
        Args:
            id (str): Message ID
            
        Returns:
            Message: Message with his full data
        """
        ...
        
    
    def markAllAsRead(self, chat_id: str) -> bool:
        """Mark all messages as read
        
        Args:
            chat_id (str): Chat ID
            
        Returns:
            bool: True if messages were marked as read, False if not
        """
        ...
        
        
    def updateStatus(self, id: str, status: int) -> Message:
        """Update a message status
        
        Args:
            id (str): Message ID
            status (int): New status
            
        Returns:
            Message: Message with his full data
        """
        ...
        
        
    def delete(self, id: str) -> bool:
        """Delete a message
        
        Args:
            id (str): Message ID
            
        Returns:
            bool: True if message was deleted, False if not
        """
        ...
        
        
    def softDelete(self, id: str) -> bool:
        """Soft delete a message
        
        Args:
            id (str): Message ID
            
        Returns:
            bool: True if message was soft deleted, False if not
        """
        ...