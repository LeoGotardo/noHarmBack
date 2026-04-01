from infrastructure.database.models.messageModel import MessageModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.message import Message
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

import sys

class MessageRepository(Message):
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
    
    def findById(self, id: str) -> Message:
        """Find a message by ID
        
        Args:
            id (str): Message ID
            
        Returns:
            Message: Message with his full data
        """
        try:
            message = self.session.query(MessageModel).filter(MessageModel.id == id).first()
            if message:
                return message
            else:
                raise NoHarmException(status_code=404, message="Message not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findByChatId(self, chat_id: str) -> list[Message]:
        """Find all messages by chat ID
        
        Args:
            chat_id (str): Chat ID
            
        Returns:
            list[Message]: List of Messages
        """
        try:
            messages = self.session.query(MessageModel).filter(MessageModel.chat == chat_id).all()
            return messages
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findUnreadByChatId(self, chat_id: str) -> list[Message]:
        """Find all unread messages by chat ID
        
        Args:
            chat_id (str): Chat ID
            
        Returns:
            list[Message]: List of Messages
        """
        try:
            messages = self.session.query(MessageModel).filter(MessageModel.chat == chat_id, MessageModel.status == config.STATUS_CODES["pending"]).all()
            return messages
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def create(self, Message: Message) -> Message:
        """Create a message
        
        Args:
            Message (Message): Message to create
            
        Returns:
            Message: Message with his full data
        """
        try:
            self.session.add(Message)
            self.session.commit()
            return Message
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def markAsRead(self, id: str) -> Message:
        """Mark a message as read
        
        Args:
            id (str): Message ID
            
        Returns:
            Message: Message with his full data
        """
        try:
            message = self.findById(id)
            message.status = config.STATUS_CODES["read"]
            self.session.commit()
            return message
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
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
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def updateStatus(self, id: str, status: int) -> Message:
        """Update a message status
        
        Args:
            id (str): Message ID
            status (int): New status
            
        Returns:
            Message: Message with his full data
        """
        try:
            message = self.findById(id)
            message.status = status
            self.session.commit()
            return message
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def delete(self, id: str) -> bool:
        """Delete a message
        
        Args:
            id (str): Message ID
            
        Returns:
            bool: True if message was deleted, False if not
        """
        try:
            message = self.findById(id)
            self.session.delete(message)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def softDelete(self, id: str) -> bool:
        """Soft delete a message

        Args:
            id (str): Message ID

        Returns:
            bool: True if message was soft deleted, False if not
        """
        try:
            message = self.findById(id)
            message.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findByChatIdPaginated(self, chat_id: str, params: PaginationParams) -> PaginatedResponse[Message]:
        """Find all messages by chat ID with pagination

        Args:
            chat_id: Chat ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[Message]: Paginated list of messages
        """
        try:
            query = self.session.query(MessageModel).filter(MessageModel.chat == chat_id)
            total = query.count()
            offset = (params.page - 1) * params.pageSize
            items = query.offset(offset).limit(params.pageSize).all()
            return createPaginatedResponse(items, total, params.page, params.pageSize)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findUnreadByChatIdPaginated(self, chat_id: str, params: PaginationParams) -> PaginatedResponse[Message]:
        """Find all unread messages by chat ID with pagination

        Args:
            chat_id: Chat ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[Message]: Paginated list of unread messages
        """
        try:
            query = self.session.query(MessageModel).filter(
                MessageModel.chat == chat_id,
                MessageModel.status == config.STATUS_CODES["unread"]
            )
            total = query.count()
            offset = (params.page - 1) * params.pageSize
            items = query.offset(offset).limit(params.pageSize).all()
            return createPaginatedResponse(items, total, params.page, params.pageSize)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')