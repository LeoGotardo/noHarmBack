from dataclasses import dataclass

@dataclass
class Streak:
    id: str
    owner_id: str
    _start: str
    _end: str
    status: int
    is_record: bool
    _created_at: str
    _updated_at: str