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


class ReportEvidenceModel(Base, TimestampMixin):
    """What a report is evidence *of* (tb_11) — a copy, not a pointer.

    A report used to be one person's account of what another person did, with
    nothing behind it. This is the copy taken at the moment the report was
    filed: the messages that were on screen, and who the reported account was
    at the time.

    Three properties the design turns on:

    - **It is a snapshot.** A foreign key into `tb_4` would be gone the day the
      reported account is purged, which is the day the evidence matters most.
      `source_id` and `author_id` are plain strings with no constraint, so the
      row survives every account it names.
    - **The server writes it.** The client names a chat; the content is copied
      out of the database by `ReportService`. Nothing a reporter types reaches
      this table, or a report would be a text box in which to invent quotes.
    - **It is tamper-evident.** `content_hash` is the keyed blind index of the
      plaintext (`Encryption.hash`), so a row edited after the fact no longer
      matches its own hash, and two captures of the same message are provably
      the same text.

    `created_at` is when the capture happened; `occurred_at` is when the thing
    captured was said. They are different questions and a moderator needs both.
    """
    __tablename__ = "tb_11"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_11a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report: Mapped[uuid.UUID] = mapped_column("cl_11b", UUID(as_uuid=True), ForeignKey("tb_10.cl_10a", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column("cl_11c", String(16), nullable=False)
    # The row this was copied from, and who wrote it. No foreign keys on
    # purpose — see the class docstring.
    source_id: Mapped[Optional[str]] = mapped_column("cl_11d", String, nullable=True)
    author_id: Mapped[Optional[str]] = mapped_column("cl_11e", String, nullable=True)
    content: Mapped[str] = mapped_column("cl_11f", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    content_hash: Mapped[str] = mapped_column("cl_11g", String(64), nullable=False)
    occurred_at: Mapped[Optional[datetime.datetime]] = mapped_column("cl_11h", DateTime, nullable=True)
