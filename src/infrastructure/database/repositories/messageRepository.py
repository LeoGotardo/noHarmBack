from core.errorUtils import excLocation
from infrastructure.database.models.messageModel import MessageModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.message import Message
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from typing import Optional

import sys

class MessageRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
        
    def _toEntity(self, model: MessageModel) -> Message:
        return Message(
            id=model.id,
            chat=model.chat,
            sender=model.sender,
            status=model.status,
            send_at=model.send_at,
            message=model.message,
            recived_at=model.recived_at,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
        
    
    def findById(self, id: str, returnModel: bool = False) -> Message | MessageModel:
        """Find a message by ID
        
        Args:
            id (str): Message ID
            
        Returns:
            Message: Message with his full data
        """
        try:
            message = self.session.query(MessageModel).filter(MessageModel.id == id).first()
            if message:
                return message if returnModel else self._toEntity(message)
            else:
                raise NoHarmException(statusCode=404, message="Message not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def findByChatId(self, chat_id: str, params: Optional[PaginationParams] = None) -> list[Message] | PaginatedResponse[Message]:
        """Find all messages by chat ID, optionally paginated

        Args:
            chat_id (str): Chat ID
            params: Optional pagination parameters

        Returns:
            list[Message] | PaginatedResponse[Message]
        """
        try:
            query = self.session.query(MessageModel).filter(MessageModel.chat == chat_id)
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                
                items = query.offset(offset).limit(params.pageSize).all()
                items = [self._toEntity(item) for item in items]
                
                return createPaginatedResponse(items, total, params.page, params.pageSize)  
            
            return [self._toEntity(item) for item in query.all()]  
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findUnreadByChatId(self, chat_id: str, params: Optional[PaginationParams] = None) -> list[Message] | PaginatedResponse[Message]:
        """Find all unread messages by chat ID, optionally paginated

        Args:
            chat_id (str): Chat ID
            params: Optional pagination parameters

        Returns:
            list[Message] | PaginatedResponse[Message]
        """
        try:
            query = self.session.query(MessageModel).filter(
                MessageModel.chat == chat_id,
                MessageModel.status == config.STATUS_CODES["unread"]
            )
            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                
                items = query.offset(offset).limit(params.pageSize).all()
                items = [self._toEntity(item) for item in items]
                
                return createPaginatedResponse(items, total, params.page, params.pageSize)  
            
            return [self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def create(self, Message: Message) -> Message:
        """Create a message
        
        Args:
            Message (Message): Message to create
            
        Returns:
            Message: Message with his full data
        """
        try:
            messageModel = MessageModel(
                chat=Message.chat,
                sender=Message.sender,
                status=Message.status,
                send_at=Message.send_at,
                message=Message.message,
                recived_at=Message.recived_at,
                created_at=Message.created_at,
                updated_at=Message.updated_at
            )
            
            self.session.add(messageModel)
            self.session.commit()
            
            return self._toEntity(messageModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def markAsRead(self, id: str) -> Message:
        """Mark a message as read
        
        Args:
            id (str): Message ID
            
        Returns:
            Message: Message with his full data
        """
        try:
            messageModel = self.findById(id, returnModel=True)
            
            messageModel.status = config.STATUS_CODES["read"]
            
            self.session.commit()
            
            return self._toEntity(messageModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def markAllAsRead(self, chat_id: str) -> bool:
        """Mark all messages as read
        
        Args:
            chat_id (str): Chat ID
            
        Returns:
            bool: True if messages were marked as read, False if not
        """
        try:
            messages = self.session.query(MessageModel).filter(MessageModel.chat == chat_id, MessageModel.status == config.STATUS_CODES["unread"]).all()
            for message in messages:
                message.status = config.STATUS_CODES["read"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def updateStatus(self, id: str, status: int) -> Message:
        """Update a message status
        
        Args:
            id (str): Message ID
            status (int): New status
            
        Returns:
            Message: Message with his full data
        """
        try:
            messageModel = self.findById(id, returnModel=True)
            messageModel.status = status
            
            self.session.commit()
            
            return self._toEntity(messageModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
    
    def update(self, id: str, updatedMessage: Message) -> Message:
        """Update a message

        Args:
            id (str): Message ID
            updatedMessage (Message): Message with updated data

        Returns:
            Message: Message with his full data
        """
        try:
            messageModel = self.findById(id, returnModel=True)
            messageModel.sender = updatedMessage.sender if updatedMessage.sender else messageModel.sender
            messageModel.status = updatedMessage.status if updatedMessage.status else messageModel.status
            
            self.session.commit()
            
            return self._toEntity(messageModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
        
    def delete(self, id: str) -> bool:
        """Delete a message
        
        Args:
            id (str): Message ID
            
        Returns:
            bool: True if message was deleted, False if not
        """
        try:
            messageModel = self.findById(id, returnModel=True)
            
            self.session.delete(messageModel)
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def softDelete(self, id: str) -> bool:
        """Soft delete a message

        Args:
            id (str): Message ID

        Returns:
            bool: True if message was soft deleted, False if not
        """
        try:
            messageModel = self.findById(id, returnModel=True)
            
            messageModel.status = config.STATUS_CODES["deleted"]
            
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

