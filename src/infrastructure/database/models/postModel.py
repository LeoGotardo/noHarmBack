from typing import Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import datetime
import uuid


class PostModel(Base, TimestampMixin):
    """A post in the Community tab (tb_16).

    `visibility` is the audience the author picked — `friends` or `community`.
    Who can actually read a post also depends on blocks and on the author's
    account, and that is decided in `PostService`, not here and not in RLS: the
    table is readable by any session, like `tb_0`.

    `status` is `enabled` while the post is up and `blocked` once a moderator
    removed it; `removed_at` starts the retention clock for
    `purge-removed-content`. The author deleting their own post is a real
    DELETE, which cascades to its comments and likes.
    """
    __tablename__ = "tb_16"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_16a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    author_id: Mapped[str] = mapped_column("cl_16b", String, ForeignKey("tb_0.cl_0a", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column("cl_16c", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    visibility: Mapped[str] = mapped_column("cl_16d", String(16), nullable=False)
    status: Mapped[int] = mapped_column("cl_16e", Integer, nullable=False)
    removed_at: Mapped[Optional[datetime.datetime]] = mapped_column("cl_16f", DateTime, nullable=True)
