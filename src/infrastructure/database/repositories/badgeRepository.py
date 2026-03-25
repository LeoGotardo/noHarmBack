from domain.entities.badge import Badge

class BadgeRepository(Badge):
    def __init__(self, db):
        self.db = db
        

    def findById(self, id: str) -> Badge:
        """Find a badge by ID
        
        Args:
            id (str): Badge ID
            
        Returns:
            Badge: Badge with his full data
        """
        ...
        
    
    def findAll(self) -> list[Badge]:
        """Find all badges
        
        Returns:
            list[Badge]: List of Badges
        """
        ...
        
    
    def create(self, Badge: Badge) -> Badge:
        """Create a badge
        
        Args:
            Badge (Badge): Badge to create
            
        Returns:
            Badge: Badge with his full data
        """
        ...
        
    
    def update(self, Badge: Badge) -> Badge:
        """Update a badge
        
        Args:
            Badge (Badge): Badge to update
            
        Returns:
            Badge: Badge with his full data
        """
        ...
        
    
    def updateStatus(self, id: str, status: int) -> Badge:
        """Update a badge status
        
        Args:
            id (str): Badge ID
            status (int): New status
            
        Returns:
            Badge: Badge with his full data
        """
        ...
        
    
    def delete(self, id: str) -> bool:
        """Delete a badge
        
        Args:
            id (str): Badge ID
            
        Returns:
            bool: True if badge was deleted, False if not
        """
        ...
        
    
    def softDelete(self, id: str) -> bool:
        """Soft delete a badge
        
        Args:
            id (str): Badge ID
            
        Returns:
            bool: True if badge was soft deleted, False if not
        """
        ...