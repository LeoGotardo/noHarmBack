from infrastructure.database.repositories.userRepository import UserRepository
from domain.entities.user import User
from core.database import Database


class UserService:
    def __init__(self, db):
        self.database: Database = db
        self.userRepository = UserRepository(self.database)
        
        
    def findById(self, id: str) -> User:
        """Find by User ID
        
        Args:
            id (str): User ID
            
        Returns:
            User: User with his full data
        """
        return self.userRepository.findById(id)
    
    
    def findByEmail(self, email: str) -> User:
        """Find a user by email
        
        Args:
            email (str): User email
            
        Returns:
            User: User with his full data
        """
        return self.userRepository.findByEmail(email)
    
    
    def findByUsername(self, username: str) -> User:
        """Find a user by username
        
        Args:
            username (str): User username
            
        Returns:
            User: User with his full data
        """
        return self.userRepository.findByUsername(username)
    
    
    def findAll(self) -> list[User]:
        """Find all users
        
        Returns:
            list[User]: List of Users
        """
        return self.userRepository.findAll()
    
    
    def create(self, User: User) -> User:
        """Create a user
        
        Args:
            User (User): User to create
            
        Returns:
            User: User with his full data
        """
        return self.userRepository.create(User)
    
    
    def update(self, user_id: str, updatedUser: User) -> User: 
        """Update a user
        
        Args:
            user_id (str): User ID
            updatedUser (User): User with updated data
            
        Returns:
            User: User with his full data
        """
        return self.userRepository.update(user_id, updatedUser)
    
    
    def updateStatus(self, id: str, status: int) -> User:
        """Update a user status
        
        Args:
            id (str): User ID
            status (int): New status
            
        Returns:
            User: User with his full data
        """
        return self.userRepository.updateStatus(id, status)
    
    
    def delete(self, id: str) -> bool:
        """Soft delete a user
        
        Args:
            id (str): User ID
            
        Returns:
            bool: True if user was deleted, False if not
        """
        return self.userRepository.softDelete(id)