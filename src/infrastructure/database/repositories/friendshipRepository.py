from domain.entities.friendship import Friendship
from core.errorUtils import excLocation
from infrastructure.database.models.friendshipModel import FriendshipModel
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from sqlalchemy import or_
from typing import Optional

import sys

class FriendshipRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine


    def _toEntity(self, model: FriendshipModel) -> Friendship:
        return Friendship(
            id=model.id,
            sender=model.sender,
            reciver=model.reciver,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at
        )


    def findById(self, id: str, returnModel: bool = False) -> Friendship | FriendshipModel:
        """Find a friendship by ID

        Args:
            id (str): Friendship ID

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendshipModel = self.session.query(FriendshipModel).filter(FriendshipModel.id == id).first()
            if friendshipModel:
                return friendshipModel if returnModel else self._toEntity(friendshipModel)
            raise NoHarmException(statusCode=404, message="Friendship not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findByUsers(self, userA: str, userB: str) -> Friendship:
        """Find a friendship between two users regardless of who sent the request

        Args:
            userA (str): First user ID
            userB (str): Second user ID

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendshipModel = self.session.query(FriendshipModel).filter(
                or_(
                    (FriendshipModel.sender == userA) & (FriendshipModel.reciver == userB),
                    (FriendshipModel.sender == userB) & (FriendshipModel.reciver == userA)
                )
            ).first()
            
            if friendshipModel:
                return self._toEntity(friendshipModel)
             
            raise NoHarmException(statusCode=404, message="Friendship not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def existsByUsers(self, userA: str, userB: str) -> bool:
        """Check if any friendship exists between two users regardless of direction

        Args:
            userA (str): First user ID
            userB (str): Second user ID

        Returns:
            bool: True if friendship exists, False if not
        """
        try:
            friendshipModel = self.session.query(FriendshipModel).filter(
                or_(
                    (FriendshipModel.sender == userA) & (FriendshipModel.reciver == userB),
                    (FriendshipModel.sender == userB) & (FriendshipModel.reciver == userA)
                )
            ).first()
            
            return friendshipModel is not None
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findAllByUserId(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        """Find all friendships for a user regardless of sender/receiver role, optionally paginated

        Args:
            userId (str): User ID
            params: Optional pagination parameters

        Returns:
            list[Friendship] | PaginatedResponse[Friendship]
        """
        try:
            query = self.session.query(FriendshipModel).filter(
                or_(FriendshipModel.sender == userId, FriendshipModel.reciver == userId)
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


    def findPendingReceived(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        """Find all pending friendship requests received by a user, optionally paginated

        Args:
            userId (str): User ID
            params: Optional pagination parameters

        Returns:
            list[Friendship] | PaginatedResponse[Friendship]
        """
        try:
            query = self.session.query(FriendshipModel).filter(
                FriendshipModel.reciver == userId,
                FriendshipModel.status == config.STATUS_CODES["pending"]
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


    def findPendingSent(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        """Find all pending friendship requests sent by a user, optionally paginated

        Args:
            userId (str): User ID
            params: Optional pagination parameters

        Returns:
            list[Friendship] | PaginatedResponse[Friendship]
        """
        try:
            query = self.session.query(FriendshipModel).filter(
                FriendshipModel.sender == userId,
                FriendshipModel.status == config.STATUS_CODES["pending"]
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
        
        
    def findBlockedUsers(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        try:
            query = self.db.session.query(FriendshipModel).filter(FriendshipModel.sender == userId, FriendshipModel.status == config.STATUS_CODES.get("blocked"))
            if params:
                query = query.offset(params.page * params.pageSize).limit(params.pageSize)
                total = query.count()
                items = [self._toEntity(item) for item in query.all()]
                
                return createPaginatedResponse(items, total, params.page, params.pageSize)  
            return [self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def create(self, Friendship: Friendship) -> Friendship:
        """Create a friendship

        Args:
            Friendship (Friendship): Friendship to create

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendshipModel = FriendshipModel(
                sender=Friendship.sender,
                reciver=Friendship.reciver,
                status=Friendship.status,
                created_at=Friendship.created_at,
                updated_at=Friendship.updated_at
            )
            
            self.session.add(friendshipModel)
            self.session.commit()
            
            return self._toEntity(friendshipModel)
        
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def updateStatus(self, id: str, status: str) -> Friendship:
        """Update a friendship status

        Args:
            id (str): Friendship ID
            status (str): New status key (e.g. "accepted", "blocked")

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendshipModel = self.findById(id, returnModel=True)

            friendshipModel.status = config.STATUS_CODES[status]

            self.session.commit()

            return self._toEntity(friendshipModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def update(self, id: str, updatedFriendship: Friendship) -> Friendship:
        """Update a friendship

        Args:
            id (str): Friendship ID
            updatedFriendship (Friendship): Friendship with updated data

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendshipModel = self.findById(id, returnModel=True)
            
            friendshipModel.sender = updatedFriendship.sender if updatedFriendship.sender else friendshipModel.sender
            friendshipModel.reciver = updatedFriendship.reciver if updatedFriendship.reciver else friendshipModel.reciver
            friendshipModel.status = updatedFriendship.status if updatedFriendship.status else friendshipModel.status
            
            self.session.commit()
            
            return self._toEntity(friendshipModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    
    def delete(self, id: str) -> bool:
        """Delete a friendship
        
        Args:
            id (str): Friendship ID
            
        Returns:
            bool: True if friendship was deleted, False if not
        """
        try:
            friendshipModel = self.findById(id, returnModel=True)
            
            self.session.delete(friendshipModel)
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def softDelete(self, id: str) -> bool:
        """Soft delete a friendship

        Args:
            id (str): Friendship ID

        Returns:
            bool: True if friendship was soft deleted, False if not
        """
        try:
            friendshipModel = self.findById(id, returnModel=True)
            
            friendshipModel.status = config.STATUS_CODES["deleted"]
            
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
