from core.errorUtils import excLocation
from infrastructure.database.models.userModel import UserModel
from exceptions.baseExceptions import NoHarmException
from domain.entities.user import User
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse
from core.database import Database
from core.config import config
from security.encryption import Encryption

from typing import Optional

class UserRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine
        
        
    def _toEntity(self, model: UserModel) -> User:
        return User(
            id=model.id,
            username=model.username,
            email=model.email,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            profile_picture=model.profile_picture
        )
        
    
    def findById(self, id: str, returnModel: bool = False) -> User | UserModel:
        """Find a user by ID
        
        Args:
            id (str): User ID
            
        Returns:
            User: User with his full data
        """
        try:
            user = self.session.query(UserModel).filter(UserModel.id == id).first()
            if user:
                return user if returnModel else self._toEntity(user)
            else:
                raise NoHarmException(statusCode=404, message="User not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
    
    def findByEmail(self, email: str) -> User:
        try:
            emailHash = Encryption.hash(email)
            
            userModel = self.session.query(UserModel).filter(UserModel.email_hash == emailHash).first()
            
            if userModel:
                return self._toEntity(userModel)
            else:
                raise NoHarmException(statusCode=404, message="User not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findByUsername(self, username: str) -> User:
        try:
            usernameHash = Encryption.hash(username)
            userModel = self.session.query(UserModel).filter(UserModel.username_hash == usernameHash).first()
            
            if userModel:
                return self._toEntity(userModel)
            else:
                raise NoHarmException(statusCode=404, message="User not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
    
    
    def findManyByIds(self, ids: list[str]) -> list[User]:
        """Fetch multiple users by ID (public profile read).

        Returns only users that exist; missing IDs are silently skipped.
        """
        if not ids:
            return []
        try:
            userModels = self.session.query(UserModel).filter(UserModel.id.in_(ids)).all()
            return [self._toEntity(u) for u in userModels]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    # Accounts in these states are excluded from the directory: a deleted or
    # banned user must not remain findable in friend search.
    _HIDDEN_STATUSES = (
        config.STATUS_CODES["deleted"],
        config.STATUS_CODES["banned"],
        config.STATUS_CODES["blocked"],
    )


    def search(self, term: str, params: Optional[PaginationParams] = None) -> list[User] | PaginatedResponse[User]:
        """Find users by an exact username or email match.

        Both columns are encrypted, so only their SHA-256 hashes are queryable —
        exact matches only, which is also what the privacy rule requires (§5).
        Without this, clients had to page the whole directory to find one person.
        """
        try:
            term = (term or "").strip()
            if not term:
                return [] if not params else createPaginatedResponse([], 0, params.page, params.pageSize)

            termHash = Encryption.hash(term)
            query = (
                self.session.query(UserModel)
                .filter(UserModel.status.notin_(self._HIDDEN_STATUSES))
                .filter((UserModel.username_hash == termHash) | (UserModel.email_hash == termHash))
            )

            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                items = [self._toEntity(item) for item in query.offset(offset).limit(params.pageSize).all()]
                return createPaginatedResponse(items, total, params.page, params.pageSize)

            return [self._toEntity(item) for item in query.all()]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findAll(self, params: Optional[PaginationParams] = None, includeInactive: bool = False) -> list[User] | PaginatedResponse[User]:
        """Find all users, optionally paginated

        Args:
            params: Optional pagination parameters (page, pageSize)
            includeInactive: Include deleted / banned / blocked accounts

        Returns:
            list[User] | PaginatedResponse[User]: List of Users or paginated response
        """
        try:
            query = self.session.query(UserModel)
            if not includeInactive:
                query = query.filter(UserModel.status.notin_(self._HIDDEN_STATUSES))
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
    
    
    def create(self, User: User) -> User:
        """Create a user
        
        Args:
            User (User): User to create
            
        Returns:
            User: User with his full data
        """
        try:
            userModel = UserModel(
                id=User.id,
                username=User.username,
                email=User.email,
                status=User.status,
                created_at=User.created_at,
                updated_at=User.updated_at,
                profile_picture=User.profile_picture
            )
            
            self.session.add(userModel)
            self.session.commit()
            
            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def update(self, user_id: str, updatedUser: User) -> User: 
        """Update a user
        
        Args:
            user_id (str): User ID
            updatedUser (User): User with updated data
            
        Returns:
            User: User with his full data
        """
        try:
            userModel = self.findById(user_id, returnModel=True)
            
            userModel.username = updatedUser.username if updatedUser.username else userModel.username
            userModel.email = updatedUser.email if updatedUser.email else userModel.email
            userModel.status = updatedUser.status if updatedUser.status else userModel.status
            userModel.profile_picture = updatedUser.profile_picture if updatedUser.profile_picture else userModel.profile_picture
            
            self.session.commit()
            
            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def updateStatus(self, id: str, status: int) -> User:
        """Update a user status
        
        Args:
            id (str): User ID
            status (int): New status
            
        Returns:
            User: User with his full data
        """
        try:
            userModel = self.findById(id, returnModel=True)
            
            userModel.status = status
            
            self.session.commit()
            
            return self._toEntity(userModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        

    def delete(self, id: str) -> bool:
        """Delete a user
        
        Args:
            id (str): User ID
            
        Returns:
            bool: True if user was deleted, False if not
        """
        try:
            userModel = self.findById(id, returnModel=True)
            
            self.session.delete(userModel)
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a user

        Args:
            id (str): User ID

        Returns:
            bool: True if user was soft deleted, False if not
        """
        try:
            userModel = self.findById(id, returnModel=True)
            
            userModel.status = config.STATUS_CODES["deleted"]
            self.session.commit()
            
            return True
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
