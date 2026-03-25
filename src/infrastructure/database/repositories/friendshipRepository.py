from domain.entities.friendship import Friendship

class FriendshipRepository(Friendship):
    def __init__(self, db):
        self.db = db