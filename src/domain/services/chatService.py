from infrastructure.database.repositories.chatRepository import ChatRepository
from domain.entities.chat import Chat
from core.database import Database
from domain.services.messageService import MessageService

from datetime import datetime


class ChatService:
    def __init__(self, db):
        self.database: Database = db
        self.chatRepository = ChatRepository(self.database)
        self.messageService = MessageService(self.database)
    
    
    def getAll(self) -> list[Chat]:
        """
        Return all chats.
        
        Returns:
            list[Chat]: list of chats
        """
        return self.chatRepository.findAll()
    
    
    def get(self, chatId: str) -> Chat:
        """
        Return a chat by ID.
        
        Args:
            chatId: ID of the chat
            
        Returns:
            Chat: chat
        """
        chat = self.chatRepository.findById(chatId)
        chat.messages = self.messageService.getByChatId(chatId)
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
    
    
    def updateStatus(self, chatId: str, status: int) -> None:
        """
        Update the status of a chat.
        
        Args:
            chatId: ID of the chat
            status: new status (ex: 1 enabled, 0 disabled)
        """
        self.chatRepository.updateStatus(chatId, status)
        
        
    def updateEndedAt(self, chatId: str, endedAt: datetime) -> None:
        """
        Update the endedAt field of a chat.
        
        Args:
            chatId: ID of the chat
            endedAt: new endedAt value
        """
        self.chatRepository.updateEndedAt(chatId, endedAt)