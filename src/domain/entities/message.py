from dataclasses import dataclass

@dataclass
class Message:
    id: str
    chat: str
    sender: str
    message: str
    status: int
    send_at: str
    recived_at: str
    created_at: str
    updated_at: str