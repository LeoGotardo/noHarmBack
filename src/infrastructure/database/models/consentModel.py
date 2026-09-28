from typing import Optional
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin

import datetime
import uuid


class ConsentModel(Base, TimestampMixin):
    """One act of agreeing to one document (tb_13).

    Append-only. Accepting a new version of the terms adds a row beside the old
    one instead of replacing it, so the table reads as the sequence of
    decisions an account made rather than a current state that forgot how it
    got there. `ConsentRepository.findCurrent` takes the newest row per
    document; everything older is history and stays.

    `document` is `terms`, `privacy` or `health_data`. The third has its own row
    rather than being folded into the first two because a tracked streak is a
    record of someone's recovery — health data, which needs consent that is
    explicit, given separately, and withdrawable on its own without closing the
    account. A single "I agree" covering all three would be none of those
    things.

    `version` is the document revision that was live when the user agreed, not
    a pointer to whatever is current. That is the whole mechanism: bumping
    `TERMS_VERSION` in config makes every stored row stale, and the app asks
    again. Comparing against a live value would mean an account had silently
    agreed to a text published after it stopped looking.

    `withdrawn_at` ends a consent without deleting it. Withdrawing health
    consent destroys the streaks it covered — but the record that the consent
    existed and was taken back has to outlive that data, because it is the only
    evidence the withdrawal was honoured.

    Nothing here is encrypted. Every column is either a UUID, a foreign key, a
    short closed-set code or a timestamp; there is no prose and no identifier
    that is not already the primary key of another table.
    """
    __tablename__ = "tb_13"

    id: Mapped[uuid.UUID] = mapped_column("cl_13a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column("cl_13b", String, ForeignKey("tb_0.cl_0a", ondelete="CASCADE"), nullable=False)
    document: Mapped[str] = mapped_column("cl_13c", String(32), nullable=False)
    version: Mapped[str] = mapped_column("cl_13d", String(32), nullable=False)
    accepted_at: Mapped[datetime.datetime] = mapped_column("cl_13e", DateTime, nullable=False)
    withdrawn_at: Mapped[Optional[datetime.datetime]] = mapped_column("cl_13f", DateTime, nullable=True)
