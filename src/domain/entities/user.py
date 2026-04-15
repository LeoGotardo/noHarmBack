from dataclasses import dataclass
from datetime import datetime

@dataclass
class User:
    id: str
    username: str
    email: str
    profile_picture: bytes
    status: int
    created_at: datetime
    updated_at: datetime