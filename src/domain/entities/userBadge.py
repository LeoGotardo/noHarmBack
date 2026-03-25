from dataclasses import dataclass

@dataclass
class UserBadge:
    id: str
    user_id: str
    badge_id: str
    _given_at: str
    status: int
    _created_at: str    
    _updated_at: str