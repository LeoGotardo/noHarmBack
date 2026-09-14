from typing import Optional
from sqlalchemy import DateTime, Integer, Text, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import datetime
import uuid


class ReportModel(Base, TimestampMixin):
    """A report filed by one user about another (tb_10).

    `reason` is a plain short code so moderation can group and filter on it.
    `details` is free text the reporter wrote about someone else's behaviour —
    the most sensitive column in the row — and is encrypted like a message
    body.

    **Two columns name the reported user, and that is deliberate.** `reported`
    is the live foreign key, and it is nullable because purging that account
    sets it to NULL instead of destroying the report: deleting your account was
    otherwise a way to erase an open complaint about you, and the reports that
    matter most are the ones people delete their account over.
    `reported_uid` is the id copied at filing time and carries no constraint,
    so the queue still knows who a report was about after the row it pointed at
    is gone. Every lookup — the duplicate check, the count against an account —
    reads `reported_uid` for exactly that reason.

    `reported_username` is the display name as it was that day. A moderator
    reading the queue a week later needs the name the reporter saw, not the one
    the account renamed itself to afterwards.
    """
    __tablename__ = "tb_10"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_10a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reporter: Mapped[Optional[str]] = mapped_column("cl_10b", String, ForeignKey("tb_0.cl_0a", ondelete="SET NULL"), nullable=True)
    reported: Mapped[Optional[str]] = mapped_column("cl_10c", String, ForeignKey("tb_0.cl_0a", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str] = mapped_column("cl_10d", String(32), nullable=False)
    details: Mapped[Optional[str]] = mapped_column("cl_10e", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=True)
    status: Mapped[int] = mapped_column("cl_10f", Integer, nullable=False)
    reported_uid: Mapped[str] = mapped_column("cl_10g", String, nullable=False)
    reported_username: Mapped[Optional[str]] = mapped_column("cl_10h", StringEncryptedType(String, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=True)
    # Who is reviewing it, and since when. "In review" is these two plus a
    # clock (`REPORT_LOCK_MINUTES`), not a status code — see migration
    # 20260911_03. No foreign key: the record of who reviewed a report outlives
    # the moderator's account.
    locked_by: Mapped[Optional[str]] = mapped_column("cl_10i", String, nullable=True)
    locked_at: Mapped[Optional[datetime.datetime]] = mapped_column("cl_10j", DateTime, nullable=True)
