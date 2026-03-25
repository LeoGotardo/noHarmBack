from domain.entities.userBadge import UserBadge

class UserBadgesRepository(UserBadge):
    def __init__(self, db):
        self.db = db