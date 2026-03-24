from dataclasses import dataclass

@dataclass
class AuditLogs:
    id: str
    type: int
    catalist_id: str
    catalist: int
    description: str
    created_at: str
    updated_at: str