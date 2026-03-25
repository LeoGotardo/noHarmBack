from domain.entities.user import User

class UserRepository(User):
    def __init__(self, db):
        self.db = db
        
    
    def findById(self, id: str) -> User:
        """Find a user by ID
        
        Args:
            id (str): User ID
            
        Returns:
            User: User with his full data
        """
        ...
    
    
    def findByEmail(self, email: str) -> User:
        """Find a user by email
        
        Args:
            email (str): User email
            
        Returns:
            User: User with his full data
        """
        ...
    
    
    def findByUsername(self, username: str) -> User:
        """Find a user by username
        
        Args:
            username (str): User username
            
        Returns:
            User: User with his full data
        """
        ...
    
    
    def findAll(self) -> list[User]:
        """Find all users
        
        Returns:
            list[User]: List of Users
        """
        ...
    
    
    def create(self, User: User) -> User:
        """Create a user
        
        Args:
            User (User): User to create
            
        Returns:
            User: User with his full data
        """
        ...
        
    
    def update(self, User: User) -> User:
        """Update a user
        
        Args:
            User (User): User to update
            
        Returns:
            User: User with his full data
        """
        ...
        
    
    def updateStatus(self, id: str, status: int) -> User:
        """Update a user status
        
        Args:
            id (str): User ID
            status (int): New status
            
        Returns:
            User: User with his full data
        """
        ...
        

    def delete(self, id: str) -> bool:
        """Delete a user
        
        Args:
            id (str): User ID
            
        Returns:
            bool: True if user was deleted, False if not
        """
        ...
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a user
        
        Args:
            id (str): User ID
            
        Returns:
            bool: True if user was soft deleted, False if not
        """
        ...