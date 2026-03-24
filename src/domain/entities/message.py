from dataclasses import dataclass

@dataclass
class Message:
    id: str
    chat: str
    sender: str
    _message: str
    status: int
    send_at: str
    recived_at: str
    _created_at: str
    _updated_at: str