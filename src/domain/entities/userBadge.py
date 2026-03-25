from dataclasses import dataclass

@dataclass
class UserBadge:
    id: str
    user_id: str
    badge_id: str
    given_at: str
    status: int
    created_at: str    
    updated_at: str