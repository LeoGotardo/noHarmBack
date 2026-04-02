from infrastructure.database.repositories.messageRepository import MessageRepository
from domain.entities.message import Message
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from core.database import Database
from typing import Optional

from datetime import datetime

class MessageService:
    def __init__(self, db):
        self.database: Database = db
        self.messageRepository = MessageRepository(self.database)
        
    
    def getByChatId(self, chatId: str, params: Optional[PaginationParams] = None) -> list[Message] | PaginatedResponse[Message]:
        """
        Return all chat messages, optionally paginated.

        Args:
            chatId: ID of the chat
            params: Optional pagination parameters

        Returns:
            list[Message] | PaginatedResponse[Message]
        """
        return self.messageRepository.findByChatId(chatId, params)
    
    
    def get(self, messageId: str) -> Message:
        """
        Return a message by ID.
        
        Args:
            messageId: ID of the message
            
        Returns:
            Message: message
        """
        return self.messageRepository.findById(messageId)
    
    
    def getUnreadByChatId(self, chatId: str, params: Optional[PaginationParams] = None) -> list[Message] | PaginatedResponse[Message]:
        """
        Return all unread chat messages, optionally paginated.

        Args:
            chatId: ID of the chat
            params: Optional pagination parameters

        Returns:
            list[Message] | PaginatedResponse[Message]
        """
        return self.messageRepository.findUnreadByChatId(chatId, params)
    
    
    def markAsRead(self, messageId: str) -> Message:
        """
        Mark a message as read.
        
        Args:
            messageId: ID of the message
            
        Returns:
            Message: updated message
        """
        return self.messageRepository.markAsRead(messageId)
    
    
    def markAllAsRead(self, chatId: str) -> bool:
        """
        Mark all messages as read.
        
        Args:
            chatId: ID of the chat
            
        Returns:
            bool: True if messages were marked as read, False if not
        """
        return self.messageRepository.markAllAsRead(chatId)
    
    
    def create(self, newMessage: Message) -> Message:
        """
        Create a message.
        
        Args:
            newMessage: message to create
            
        Returns:
            Message: created message
        """
        return self.messageRepository.create(newMessage)
    
    
    def updateStatus(self, messageId: str, status: int) -> Message:
        """_summary_

        Args:
            messageId (str): message ID
            status (int): status

        Returns:
            Message: updated message
        """
        return self.messageRepository.updateStatus(messageId, status)