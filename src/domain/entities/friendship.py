from dataclasses import dataclass

@dataclass
class Friendship:
    id: str
    sender: str
    reciver: str
    send_at: str
    recived_at: str
    status: int
    created_at: str
    updated_at: str