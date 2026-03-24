from dataclasses import dataclass

@dataclass
class Friendship:
    id: str
    sender: str
    reciver: str
    send_at: str
    recived_at: str
    status: int
    _created_at: str
    _updated_at: str