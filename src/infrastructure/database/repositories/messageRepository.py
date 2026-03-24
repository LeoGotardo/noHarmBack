from domain.entities.message import Message

class MessageRepository(Message):
    def __init__(self, db):
        self.db = db