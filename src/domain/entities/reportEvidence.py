from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class ReportEvidence:
    """One captured item behind a report — a message, or the reported profile.

    `author_id` and `source_id` are plain identifiers rather than references:
    the evidence has to outlive the account it is about, which is exactly the
    account most likely to be deleted after a report (see migration
    20260911_01).
    """
    report: UUID
    kind: str
    content: str
    content_hash: Optional[str] = None
    source_id: Optional[str] = None
    author_id: Optional[str] = None
    occurred_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id: Optional[UUID] = None
