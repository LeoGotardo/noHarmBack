from domain.entities.user import User

class AuditLogsRepository(User):
    def __init__(self, db):
        self.db = db