from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID


@dataclass
class Consent:
    """One act of agreeing to one document.

    `document` is `terms`, `privacy` or `health_data`; `version` is the
    revision that was live at the moment of agreeing, which is what makes a
    stored consent go stale when the document is republished.

    `withdrawn_at` ends it without erasing it. A consent that was taken back is
    still a thing that happened, and the record of it is the only evidence the
    withdrawal was honoured.
    """
    user_id: str
    document: str
    version: str
    accepted_at: Optional[datetime] = None
    withdrawn_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    id: Optional[UUID] = None

    @property
    def active(self) -> bool:
        return self.withdrawn_at is None
