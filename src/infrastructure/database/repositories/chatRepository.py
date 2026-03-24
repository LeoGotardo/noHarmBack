from domain.entities.chat import Chat

class ChatRepository(Chat):
    def __init__(self, db):
        self.db = db