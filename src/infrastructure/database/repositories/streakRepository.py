from domain.entities.streak import Streak

class StreakRepository(Streak):
    def __init__(self, db):
        self.db = db