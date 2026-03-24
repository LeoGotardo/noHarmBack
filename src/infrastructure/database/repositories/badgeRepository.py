from domain.entities.badge import Badge

class BadgeRepository(Badge):
    def __init__(self, db):
        self.db = db