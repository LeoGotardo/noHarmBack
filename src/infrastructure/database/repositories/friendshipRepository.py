from domain.entities.friendship import Friendship
from infrastructure.database.models.friendshipModel import FriendshipModel
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from sqlalchemy import or_
from typing import Optional

import sys

class FriendshipRepository(Friendship):
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine


    def findById(self, id: str) -> Friendship:
        """Find a friendship by ID

        Args:
            id (str): Friendship ID

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendship = self.session.query(FriendshipModel).filter(FriendshipModel.id == id).first()
            if friendship:
                return friendship
            raise NoHarmException(status_code=404, message="Friendship not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def findByUsers(self, userA: str, userB: str) -> Friendship:
        """Find a friendship between two users regardless of who sent the request

        Args:
            userA (str): First user ID
            userB (str): Second user ID

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendship = self.session.query(FriendshipModel).filter(
                or_(
                    (FriendshipModel.sender == userA) & (FriendshipModel.reciver == userB),
                    (FriendshipModel.sender == userB) & (FriendshipModel.reciver == userA)
                )
            ).first()
            if friendship:
                return friendship
            raise NoHarmException(status_code=404, message="Friendship not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def existsByUsers(self, userA: str, userB: str) -> bool:
        """Check if any friendship exists between two users regardless of direction

        Args:
            userA (str): First user ID
            userB (str): Second user ID

        Returns:
            bool: True if friendship exists, False if not
        """
        try:
            friendship = self.session.query(FriendshipModel).filter(
                or_(
                    (FriendshipModel.sender == userA) & (FriendshipModel.reciver == userB),
                    (FriendshipModel.sender == userB) & (FriendshipModel.reciver == userA)
                )
            ).first()
            return friendship is not None
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


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
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            return query.all()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


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
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            return query.all()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


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
                return createPaginatedResponse(items, total, params.page, params.pageSize)
            return query.all()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def create(self, Friendship: Friendship) -> Friendship:
        """Create a friendship

        Args:
            Friendship (Friendship): Friendship to create

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            self.session.add(Friendship)
            self.session.commit()
            return Friendship
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def updateStatus(self, id: str, status: str) -> Friendship:
        """Update a friendship status

        Args:
            id (str): Friendship ID
            status (str): New status key (e.g. "accepted", "blocked")

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendship = self.findById(id)
            friendship.status = config.STATUS_CODES[status]
            self.session.commit()
            return friendship
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def update(self, id: str, updatedFriendship: Friendship) -> Friendship:
        """Update a friendship

        Args:
            id (str): Friendship ID
            updatedFriendship (Friendship): Friendship with updated data

        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendship = self.findById(id)
            friendship.sender = updatedFriendship.sender if updatedFriendship.sender else friendship.sender
            friendship.reciver = updatedFriendship.reciver if updatedFriendship.reciver else friendship.reciver
            friendship.status = updatedFriendship.status if updatedFriendship.status else friendship.status
            self.session.commit()
            return friendship
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')


    def softDelete(self, id: str) -> bool:
        """Soft delete a friendship

        Args:
            id (str): Friendship ID

        Returns:
            bool: True if friendship was soft deleted, False if not
        """
        try:
            friendship = self.findById(id)
            friendship.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
