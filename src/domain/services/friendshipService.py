from infrastructure.database.repositories.friendshipRepository import FriendshipRepository
from domain.entities.friendship import Friendship
from schemas.paginationSchemas import PaginationParams, PaginatedResponse
from core.database import Database

from typing import Optional


class FriendshipService:
    def __init__(self, db):
        self.database: Database = db
        self.friendshipRepository = FriendshipRepository(self.database)


    def get(self, friendshipId: str) -> Friendship:
        """Find a friendship by ID

        Args:
            friendshipId (str): Friendship ID

        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.findById(friendshipId)


    def getByUsers(self, userA: str, userB: str) -> Friendship:
        """Find a friendship between two users regardless of who sent the request

        Args:
            userA (str): First user ID
            userB (str): Second user ID

        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.findByUsers(userA, userB)


    def getAll(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        """Find all friendships for a user regardless of sender/receiver role, optionally paginated

        Args:
            userId (str): User ID
            params: Optional pagination parameters

        Returns:
            list[Friendship] | PaginatedResponse[Friendship]
        """
        return self.friendshipRepository.findAllByUserId(userId, params)


    def getPendingReceived(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        """Find all pending friendship requests received by a user, optionally paginated

        Args:
            userId (str): User ID
            params: Optional pagination parameters

        Returns:
            list[Friendship] | PaginatedResponse[Friendship]
        """
        return self.friendshipRepository.findPendingReceived(userId, params)


    def getPendingSent(self, userId: str, params: Optional[PaginationParams] = None) -> list[Friendship] | PaginatedResponse[Friendship]:
        """Find all pending friendship requests sent by a user, optionally paginated

        Args:
            userId (str): User ID
            params: Optional pagination parameters

        Returns:
            list[Friendship] | PaginatedResponse[Friendship]
        """
        return self.friendshipRepository.findPendingSent(userId, params)


    def existsByUsers(self, userA: str, userB: str) -> bool:
        """Check if any friendship exists between two users

        Args:
            userA (str): First user ID
            userB (str): Second user ID

        Returns:
            bool: True if friendship exists, False if not
        """
        return self.friendshipRepository.existsByUsers(userA, userB)


    def create(self, newFriendship: Friendship) -> Friendship:
        """Create a friendship

        Args:
            newFriendship (Friendship): Friendship to create

        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.create(newFriendship)


    def accept(self, friendshipId: str) -> Friendship:
        """Accept a friendship request

        Args:
            friendshipId (str): Friendship ID

        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.updateStatus(friendshipId, "accepted")


    def reject(self, friendshipId: str) -> Friendship:
        """Reject (ignore) a friendship request

        Args:
            friendshipId (str): Friendship ID

        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.updateStatus(friendshipId, "ignored")


    def block(self, friendshipId: str) -> Friendship:
        """Block a friendship

        Args:
            friendshipId (str): Friendship ID

        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.updateStatus(friendshipId, "blocked")


    def updateStatus(self, id: str, status: str) -> Friendship:
        """Update the status of a friendship

        Args:
            id (str): Friendship ID
            status (str): New status key (e.g. "accepted", "blocked")

        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.updateStatus(id, status)


    def update(self, friendshipId: str, updatedFriendship: Friendship) -> Friendship:
        """Update a friendship

        Args:
            friendshipId (str): Friendship ID
            updatedFriendship (Friendship): Friendship with updated data

        Returns:
            Friendship: Friendship with his full data
        """
        return self.friendshipRepository.update(friendshipId, updatedFriendship)


    def delete(self, id: str) -> bool:
        """Soft delete a friendship

        Args:
            id (str): Friendship ID

        Returns:
            bool: True if friendship was deleted, False if not
        """
        return self.friendshipRepository.softDelete(id)
