from typing import Optional
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import datetime
import uuid


class ModerationNoticeModel(Base, TimestampMixin):
    """What moderation tells the user about their own account (tb_12).

    Every other table here records what happened. This one is the only place
    the decision is said *to the person it was about* — and until it existed,
    the ladder in the moderation policy had no second rung: an account could be
    banned or left alone, and a warning was a thing a moderator could think but
    not send.

    Four kinds:

    - `warning` — nothing changes about the account. A moderator reviewed a
      report, agreed with it, and is saying so once.
    - `suspension` — written beside the ban, so that when the account comes
      back the person is not guessing what happened.
    - `rename` — the username was reset to a generated handle and the account
      must choose a real one before it can be used again.
    - `picture` — the profile picture was removed and cannot be replaced until
      a moderator lifts the block.

    The last two change the account without limiting it: the account keeps its
    streak, its friends and its history, because the problem was a name or a
    photo and the sanction is exactly that wide.

    What a notice must never carry is who reported them. The whole promise that
    makes reporting usable is that the reported user is never told, and a
    notice naming the conduct (`reason`) rather than the complainant is what
    keeps that true. `message` is the moderator's own words and is encrypted
    like a report's details, for the same reason — it is prose about a person.

    `acknowledged_at` is when the user tapped "I understand". Unacknowledged
    notices are shown on the next open; an acknowledged one is history.
    """
    __tablename__ = "tb_12"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_12a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column("cl_12b", String, ForeignKey("tb_0.cl_0a", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column("cl_12c", String(16), nullable=False)
    reason: Mapped[str] = mapped_column("cl_12d", String(32), nullable=False)
    message: Mapped[Optional[str]] = mapped_column("cl_12e", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=True)
    # The moderator who sent it. No foreign key: who decided what has to outlive
    # that person's account, the same as everywhere else in moderation.
    issued_by: Mapped[Optional[str]] = mapped_column("cl_12f", String, nullable=True)
    acknowledged_at: Mapped[Optional[datetime.datetime]] = mapped_column("cl_12g", DateTime, nullable=True)
