from infrastructure.database.repositories.chatRepository import ChatRepository
from domain.entities.chat import Chat
from core.database import Database

from datetime import datetime


class ChatService:
    def __init__(self, db):
        self.database: Database = db
        self.chatRepository = ChatRepository(self.database)
    
    
    def getAllByUserId(self, userId: str) -> list[Chat]:
        """
        Return all chats.
        
        Returns:
            list[Chat]: list of chats
        """
        return self.chatRepository.findByParticipant(userId)
    
    
    def get(self, chatId: str) -> Chat:
        """
        Return a chat by ID.
        
        Args:
            chatId: ID of the chat
            
        Returns:
            Chat: chat
        """
        chat = self.chatRepository.findById(chatId)
        return chat
    
    
    def create(self, newChat: Chat) -> Chat:
        """
        Create a chat.
        
        Args:
            newChat: chat to create
            
        Returns:
            Chat: created chat
        """
        return self.chatRepository.create(newChat)
    
    
    def updateStatus(self, chatId: str, status: int) -> Chat:
        """
        Update the status of a chat.
        
        Args:
            chatId: ID of the chat
            status: new status (ex: 1 enabled, 0 disabled)
            
        Returns:
            Chat: updated chat
        """
        self.chatRepository.updateStatus(chatId, status)
        
        
    def updateEndedAt(self, chatId: str, endedAt: datetime) -> Chat:
        """
        Update the endedAt field of a chat.
        
        Args:
            chatId: ID of the chat
            endedAt: new endedAt value
            
        Returns:
            Chat: updated chat
        """
        self.chatRepository.updateEndedAt(chatId, endedAt)
        
        
    def delete(self, chatId: str) -> bool:
        """
        Soft delete a chat.
        
        Args:
            chatId: ID of the chat
        
        Returns:
            bool: True if chat was deleted, False if not
        """
        
        return self.chatRepository.softDelete(chatId)