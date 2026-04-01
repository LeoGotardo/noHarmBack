from infrastructure.database.models.chatModel import ChatModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.chat import Chat
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from datetime import datetime

import sys


class ChatRepository(Chat):
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
        
    def findById(self, id: str) -> Chat:
        """Find a chat by ID
        
        Args:
            id (str): Chat ID
            
        Returns:
            Chat: Chat with his full data
        """
        try:
            chat = self.session.query(ChatModel).filter(ChatModel.id == id).first()
            if chat:
                return chat
            else:
                raise NoHarmException(status_code=404, message="Chat not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findByParticipant(self, participant_id: str) -> list[Chat]:
        """Find all chats by participant ID
        
        Args:
            participant_id (str): Participant ID
            
        Returns:
            list[Chat]: List of Chats
        """
        try:
            chats = self.session.query(ChatModel).filter(ChatModel.reciver == participant_id, ChatModel.status == config.STATUS_CODES["pending"]).all()
            return chats
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findAllBySenderId(self, user_id: str) -> list[Chat]:
        """Find all chats by user ID
        
        Args:
            user_id (str): User ID
            
        Returns:
            list[Chat]: List of Chats
        """
        try:
            chats = self.session.query(ChatModel).filter(ChatModel.sender == user_id).all()
            return chats
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def findAllByReciverId(self, user_id: str) -> list[Chat]:
        """Find all chats by user ID
        
        Args:
            user_id (str): User ID
            
        Returns:
            list[Chat]: List of Chats
        """
        try:
            chats = self.session.query(ChatModel).filter(ChatModel.reciver == user_id).all()
            return chats
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def create(self, chat: Chat) -> Chat:
        """Create a chat
        
        Args:
            chat (Chat): chat to create
            
        Returns:
            Chat: Chat with his full data
        """
        try:
            self.session.add(chat)
            self.session.commit()
            return Chat
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def updateStatus(self, id: str, status: int) -> Chat:
        """Update a chat status
        
        Args:
            id (str): Chat ID
            status (int): New status
            
        Returns:
            Chat: Chat with his full data
        """
        try:
            chat = self.findById(id)
            chat.status = status
            self.session.commit()
            return chat
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def updateEndedAt(self, id: str, ended_at: datetime) -> Chat:
        """Update a chat ended at
        
        Args:
            id (str): Chat ID
            ended_at (datetime): New ended at
            
        Returns:
            Chat: Chat with his full data
        """
        try:
            chat = self.findById(id)
            chat.ended_at = ended_at
            self.session.commit()
            return chat
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def delete(self, id: str) -> bool:
        """Delete a chat
        
        Args:
            id (str): Chat ID
            
        Returns:
            bool: True if chat was deleted, False if not
        """
        try:
            chat = self.findById(id)
            self.session.delete(chat)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def softDelete(self, id: str) -> bool:
        """Soft delete a chat

        Args:
            id (str): Chat ID

        Returns:
            bool: True if chat was soft deleted, False if not
        """
        try:
            chat = self.findById(id)
            chat.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findAllBySenderIdPaginated(self, user_id: str, params: PaginationParams) -> PaginatedResponse[Chat]:
        """Find all chats by sender ID with pagination

        Args:
            user_id: Sender user ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[Chat]: Paginated list of chats
        """
        try:
            query = self.session.query(ChatModel).filter(ChatModel.sender == user_id)
            total = query.count()
            offset = (params.page - 1) * params.pageSize
            items = query.offset(offset).limit(params.pageSize).all()
            return createPaginatedResponse(items, total, params.page, params.pageSize)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findAllByReciverIdPaginated(self, user_id: str, params: PaginationParams) -> PaginatedResponse[Chat]:
        """Find all chats by receiver ID with pagination

        Args:
            user_id: Receiver user ID
            params: Pagination parameters

        Returns:
            PaginatedResponse[Chat]: Paginated list of chats
        """
        try:
            query = self.session.query(ChatModel).filter(ChatModel.reciver == user_id)
            total = query.count()
            offset = (params.page - 1) * params.pageSize
            items = query.offset(offset).limit(params.pageSize).all()
            return createPaginatedResponse(items, total, params.page, params.pageSize)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')