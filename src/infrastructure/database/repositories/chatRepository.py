from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse
from infrastructure.database.models.chatModel import ChatModel
from exceptions.baseExceptions import NoHarmException
from core.errorUtils import excLocation
from domain.entities.chat import Chat
from core.database import Database
from core.config import config
from datetime import datetime
from typing import Optional
from sqlalchemy import or_, and_
from uuid import UUID


class ChatRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
    
    def _toEntity(self, model: ChatModel) -> Chat:
        return Chat(
            id=model.id,
            sender=model.sender,
            reciver=model.reciver,
            started_at=model.started_at,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            ended_at=model.ended_at
        )
    
        
    def findById(self, id: UUID, returnModel: bool = False) -> Chat | ChatModel:
        """Find a chat by ID
        
        Args:
            id (UUID): Chat ID
            
        Returns:
            Chat: Chat with his full data
        """
        try:
            chatModel = self.session.query(ChatModel).filter(ChatModel.id == id).first()
            if chatModel:
                return chatModel if returnModel else self._toEntity(chatModel)
            else:
                raise NoHarmException(statusCode=404, message="Chat not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def findByParticipant(self, participant_id: str) -> list[Chat]:
        """Find all chats by participant ID
        
        Args:
            participant_id (str): Participant ID
            
        Returns:
            list[Chat]: List of Chats
        """
        try:
            chatsModels = self.session.query(ChatModel).filter(
                or_(ChatModel.sender == participant_id, ChatModel.reciver == participant_id),
                ChatModel.status != config.STATUS_CODES["deleted"]
            ).all()
            return [self._toEntity(item) for item in chatsModels]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def findBetween(self, userA: str, userB: str) -> Chat | None:
        """Find all chats between two users, optionally paginated

        Args:
            userA (str): User A ID
            userB (str): User B ID
            params: Optional pagination parameters

        Returns:
            Chat
        """
        try:
            query = self.session.query(ChatModel).filter(
                or_(
                    and_(ChatModel.sender == userA, ChatModel.reciver == userB),
                    and_(ChatModel.sender == userB, ChatModel.reciver == userA)
                )
            )

            chat = query.first()
            
            return self._toEntity(chat) if chat else None
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findAllBySenderId(self, user_id: str, params: Optional[PaginationParams] = None) -> list[Chat] | PaginatedResponse[Chat]:
        """Find all chats by sender ID, optionally paginated

        Args:
            user_id (str): User ID
            params: Optional pagination parameters

        Returns:
            list[Chat] | PaginatedResponse[Chat]
        """
        try:
            query = self.session.query(ChatModel).filter(ChatModel.sender == user_id)
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


    def findAllByReciverId(self, user_id: str, params: Optional[PaginationParams] = None) -> list[Chat] | PaginatedResponse[Chat]:
        """Find all chats by receiver ID, optionally paginated

        Args:
            user_id (str): User ID
            params: Optional pagination parameters

        Returns:
            list[Chat] | PaginatedResponse[Chat]
        """
        try:
            query = self.session.query(ChatModel).filter(ChatModel.reciver == user_id)
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
        
        
    def create(self, chat: Chat) -> Chat:
        """Create a chat
        
        Args:
            chat (Chat): chat to create
            
        Returns:
            Chat: Chat with his full data
        """
        try:
            chatModel = ChatModel(
                sender=chat.sender,
                reciver=chat.reciver,
                started_at=chat.started_at,
                status=chat.status,
                messages=chat.messages,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
                ended_at=chat.ended_at
            )
            self.session.add(chatModel)
            self.session.commit()
            
            return self._toEntity(chatModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def updateStatus(self, id: UUID, status: int) -> Chat:
        """Update a chat status
        
        Args:
            id (UUID): Chat ID
            status (int): New status
            
        Returns:
            Chat: Chat with his full data
        """
        try:
            chatModel = self.findById(id, returnModel=True)
            chatModel.status = status
            self.session.commit()
            
            return self._toEntity(chatModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def update(self, id: UUID, updatedChat: Chat) -> Chat:
        """Update a chat    
        
        Args:
            id (UUID): Chat ID
            updatedChat (Chat): Chat with updated data
            
        Returns:
            Chat: Chat with his full data
        """
        try:
            chatModel = self.findById(id, returnModel=True)
            
            chatModel.sender = updatedChat.sender if updatedChat.sender else chatModel.sender
            chatModel.reciver = updatedChat.reciver if updatedChat.reciver else chatModel.reciver
            chatModel.status = updatedChat.status if updatedChat.status else chatModel.status
            chatModel.ended_at = updatedChat.ended_at if updatedChat.ended_at else chatModel.ended_at
            
            self.session.commit()
            
            return self._toEntity(chatModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
        
    def updateEndedAt(self, id: UUID, ended_at: datetime) -> Chat:
        """Update a chat ended at
        
        Args:
            id (UUID): Chat ID
            ended_at (datetime): New ended at
            
        Returns:
            Chat: Chat with his full data
        """
        try:
            chatModel = self.findById(id, returnModel=True)
            
            chatModel.ended_at = ended_at  
            
            self.session.commit()
            
            return self._toEntity(chatModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def delete(self, id: UUID) -> bool:
        """Delete a chat
        
        Args:
            id (UUID): Chat ID
            
        Returns:
            bool: True if chat was deleted, False if not
        """
        try:
            chatModel = self.findById(id, returnModel=True)
            
            self.session.delete(chatModel)
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
        
    def softDelete(self, id: UUID) -> bool:
        """Soft delete a chat

        Args:
            id (UUID): Chat ID

        Returns:
            bool: True if chat was soft deleted, False if not
        """
        try:
            chatModel = self.findById(id, returnModel=True)
            
            chatModel.status = config.STATUS_CODES["deleted"]
            
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

