from dataclasses import dataclass

@dataclass
class Streak:
    id: str
    owner_id: str
    start: str
    end: str
    status: int
    is_record: bool
    created_at: str
    updated_at: str