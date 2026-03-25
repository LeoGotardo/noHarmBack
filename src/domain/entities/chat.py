from dataclasses import dataclass

@dataclass
class Chat:
    id: str
    sender: str
    reciver: str
    started_at: str
    ended_at: str
    status: int
    messages: list
    created_at: str
    updated_at: str