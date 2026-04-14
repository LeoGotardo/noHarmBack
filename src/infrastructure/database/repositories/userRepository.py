from infrastructure.database.models.userModel import UserModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.user import User
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse
from core.database import Database
from core.config import config

from typing import Optional

import sys

class UserRepository(User):
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
    
    def findById(self, id: str) -> User:
        """Find a user by ID
        
        Args:
            id (str): User ID
            
        Returns:
            User: User with his full data
        """
        try:
            user = self.session.query(UserModel).filter(UserModel.id == id).first()
            if user:
                return user
            else:
                raise NoHarmException(status_code=404, message="User not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
    
    
    def findByEmail(self, email: str) -> User:
        """Find a user by email
        
        Args:
            email (str): User email
            
        Returns:
            User: User with his full data
        """
        try:
            user = self.session.query(UserModel).filter(UserModel.email == email).first()
            if user:
                return user
            else:
                raise NoHarmException(status_code=404, message="User not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
    
    
    def findByUsername(self, username: str) -> User:
        """Find a user by username
        
        Args:
            username (str): User username
            
        Returns:
            User: User with his full data
        """
        try:
            user = self.session.query(UserModel).filter(UserModel.username == username).first()
            if user:
                return user
            else:
                raise NoHarmException(status_code=404, message="User not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
    
    
    def findAll(self, params: Optional[PaginationParams] = None) -> list[User] | PaginatedResponse[User]:
        """Find all users, optionally paginated

        Args:
            params: Optional pagination parameters (page, pageSize)

        Returns:
            list[User] | PaginatedResponse[User]: List of Users or paginated response
        """
        try:
            query = self.session.query(UserModel)
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
    
    
    def create(self, User: User) -> User:
        """Create a user
        
        Args:
            User (User): User to create
            
        Returns:
            User: User with his full data
        """
        try:
            self.session.add(User)
            self.session.commit()
            return User
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def update(self, user_id: str, updatedUser: User) -> User: 
        """Update a user
        
        Args:
            user_id (str): User ID
            updatedUser (User): User with updated data
            
        Returns:
            User: User with his full data
        """
        try:
            user = self.findById(user_id)
            
            user.username = updatedUser.username if updatedUser.username else user.username
            user.email = updatedUser.email if updatedUser.email else user.email
            user.status = updatedUser.status if updatedUser.status else user.status
            user.profile_picture = updatedUser.profile_picture if updatedUser.profile_picture else user.profile_picture
            
            self.session.commit()
            return user
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def updateStatus(self, id: str, status: int) -> User:
        """Update a user status
        
        Args:
            id (str): User ID
            status (int): New status
            
        Returns:
            User: User with his full data
        """
        try:
            user = self.findById(id)
            user.status = status
            self.session.commit()
            return user
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        

    def delete(self, id: str) -> bool:
        """Delete a user
        
        Args:
            id (str): User ID
            
        Returns:
            bool: True if user was deleted, False if not
        """
        try:
            user = self.findById(id)
            self.session.delete(user)
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a user

        Args:
            id (str): User ID

        Returns:
            bool: True if user was soft deleted, False if not
        """
        try:
            user = self.findById(id)
            user.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(status_code=500, message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}')
