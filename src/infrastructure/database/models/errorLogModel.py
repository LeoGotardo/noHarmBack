from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import datetime
import uuid


class ErrorLogModel(Base, TimestampMixin):
    """A distinct fault (tb_14) — one row per *kind* of failure, not per hit.

    `main.py` has always caught everything and called `logger.exception`; that
    went to stdout and out again at the 10 MB rotation, so "has this been
    failing all week?" had no answer. This is that answer.

    Two properties the table turns on:

    - **Grouped by `fingerprint`.** A crash loop is one fault that happened
      four thousand times, and the useful shape of that is a row with a count,
      not four thousand rows. A repeat moves `last_seen` and bumps `count`.
    - **`message` and `traceback` are encrypted; nothing else is.** A
      SQLAlchemy exception carries the statement's parameters, so a failure in
      `messageService` puts a message body in the traceback and one in
      `userService` puts an e-mail there — the very values `tb_4` and `tb_0`
      encrypt. The type, path, status and fingerprint stay readable because
      they are what grouping runs on and they carry nobody's words.
    """

    __tablename__ = "tb_14"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_14a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column("cl_14b", String(16), nullable=False)
    path: Mapped[str] = mapped_column("cl_14c", String(512), nullable=False)
    method: Mapped[str] = mapped_column("cl_14d", String(8), nullable=False)
    fingerprint: Mapped[str] = mapped_column("cl_14e", String(64), nullable=False, unique=True)
    exception_type: Mapped[str] = mapped_column("cl_14f", String(128), nullable=False)
    status_code: Mapped[int] = mapped_column("cl_14g", Integer, nullable=False)
    last_seen: Mapped[datetime.datetime] = mapped_column("cl_14h", DateTime, nullable=False)
    count: Mapped[int] = mapped_column("cl_14i", Integer, nullable=False, default=1, server_default="1")
    message: Mapped[Optional[str]] = mapped_column(
        "cl_14j", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=True
    )
    traceback: Mapped[Optional[str]] = mapped_column(
        "cl_14k", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=True
    )
    # SET NULL, like tb_7.cl_7c: an error outlives the account that happened to
    # be making the request when it fired.
    user_id: Mapped[Optional[str]] = mapped_column(
        "cl_14l", String, ForeignKey("tb_0.cl_0a", ondelete="SET NULL"), nullable=True
    )
