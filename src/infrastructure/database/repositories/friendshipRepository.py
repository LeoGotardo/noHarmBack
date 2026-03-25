from domain.entities.friendship import Friendship
from infrastructure.database.models.friendshipModel import FriendshipModel
from exceptions.baseExceptions import NoHarmException

from core.database import Database
from core.config import config

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
            else:
                raise NoHarmException(status_code=404, message="Friendship not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def findByPair(self, sender_id: str, reciver_id: str) -> Friendship:
        """Find a friendship by pair
        
        Args:
            sender_id (str): Sender ID
            reciver_id (str): Reciver ID
            
        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendship = self.session.query(FriendshipModel).filter(FriendshipModel.sender == sender_id, FriendshipModel.reciver == reciver_id).first()
            if friendship:
                return friendship
            else:
                raise NoHarmException(status_code=404, message="Friendship not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findAllByReciverPending(self, reciver_id: str) -> list[Friendship]:
        """Find all friendships by reciver ID
        
        Args:
            reciver_id (str): Reciver ID
            
        Returns:
            list[Friendship]: List of Friendships
        """
        try:
            friendships = self.session.query(FriendshipModel).filter(FriendshipModel.reciver == reciver_id, FriendshipModel.status == config.STATUS_CODES["pending"]).all()
            return friendships
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def findAllBySenderPending(self, sender_id: str) -> list[Friendship]:
        """Find all friendships by sender ID
        
        Args:
            sender_id (str): Sender ID
            
        Returns:
            list[Friendship]: List of Friendships
        """
        try:
            friendships = self.session.query(FriendshipModel).filter(FriendshipModel.sender == sender_id, FriendshipModel.status == config.STATUS_CODES["pending"]).all()
            return friendships
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
        
    def findAllBySenderId(self, sender_id: str) -> list[Friendship]:
        """Find all friendships by sender ID
        
        Args:
            sender_id (str): Sender ID
            
        Returns:
            list[Friendship]: List of Friendships
        """
        try:
            friendships = self.session.query(FriendshipModel).filter(FriendshipModel.sender == sender_id).all()
            return friendships
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def findAllByReciverId(self, reciver_id: str) -> list[Friendship]:
        """Find all friendships by reciver ID
        
        Args:
            reciver_id (str): Reciver ID
            
        Returns:
            list[Friendship]: List of Friendships
        """
        try:
            friendships = self.session.query(FriendshipModel).filter(FriendshipModel.reciver == reciver_id).all()
            return friendships
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
        
    
    def updateStatus(self, id: str, status: int) -> Friendship:
        """Update a friendship status
        
        Args:
            id (str): Friendship ID
            status (int): New status
            
        Returns:
            Friendship: Friendship with his full data
        """
        try:
            friendship = self.findById(id)
            friendship.status = status
            self.session.commit()
            return friendship
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def delete(self, id: str) -> bool:
        """Delete a friendship
        
        Args:
            id (str): Friendship ID
            
        Returns:
            bool: True if friendship was deleted, False if not
        """
        try:
            friendship = self.findById(id)
            self.session.delete(friendship)
            self.session.commit()
            return True
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