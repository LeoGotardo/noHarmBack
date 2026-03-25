from domain.entities.friendship import Friendship

class FriendshipRepository(Friendship):
    def __init__(self, db):
        self.db = db
        
        
    def findById(self, id: str) -> Friendship:
        """Find a friendship by ID
        
        Args:
            id (str): Friendship ID
            
        Returns:
            Friendship: Friendship with his full data
        """
        ...
        
        
    def findByPair(self, sender_id: str, reciver_id: str) -> Friendship:
        """Find a friendship by pair
        
        Args:
            sender_id (str): Sender ID
            reciver_id (str): Reciver ID
            
        Returns:
            Friendship: Friendship with his full data
        """
        ...
        
    
    def findAllByReciverPending(self, reciver_id: str) -> list[Friendship]:
        """Find all friendships by reciver ID
        
        Args:
            reciver_id (str): Reciver ID
            
        Returns:
            list[Friendship]: List of Friendships
        """
        ...
        
        
    def findAllBySenderPending(self, sender_id: str) -> list[Friendship]:
        """Find all friendships by sender ID
        
        Args:
            sender_id (str): Sender ID
            
        Returns:
            list[Friendship]: List of Friendships
        """
        
        
    def findAllBySenderId(self, sender_id: str) -> list[Friendship]:
        """Find all friendships by sender ID
        
        Args:
            sender_id (str): Sender ID
            
        Returns:
            list[Friendship]: List of Friendships
        """
        ...
        
    
    def findAllByReciverId(self, reciver_id: str) -> list[Friendship]:
        """Find all friendships by reciver ID
        
        Args:
            reciver_id (str): Reciver ID
            
        Returns:
            list[Friendship]: List of Friendships
        """
        ...
        
    
    def create(self, Friendship: Friendship) -> Friendship:
        """Create a friendship
        
        Args:
            Friendship (Friendship): Friendship to create
            
        Returns:
            Friendship: Friendship with his full data
        """
        ...
        
    
    def updateStatus(self, id: str, status: int) -> Friendship:
        """Update a friendship status
        
        Args:
            id (str): Friendship ID
            status (int): New status
            
        Returns:
            Friendship: Friendship with his full data
        """
        ...
        
    
    def delete(self, id: str) -> bool:
        """Delete a friendship
        
        Args:
            id (str): Friendship ID
            
        Returns:
            bool: True if friendship was deleted, False if not
        """
        ...
        
        
    def softDelete(self, id: str) -> bool:
        """Soft delete a friendship
        
        Args:
            id (str): Friendship ID
            
        Returns:
            bool: True if friendship was soft deleted, False if not
        """
        ...