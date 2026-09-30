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


class PostCommentModel(Base, TimestampMixin):
    """A comment under a post (tb_17).

    Deleted by its author or by the author of the post (D7); removed by a
    moderator as a status, like a post, so an appeal can restore it.
    """
    __tablename__ = "tb_17"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_17a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column("cl_17b", UUID(as_uuid=True), ForeignKey("tb_16.cl_16a", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[str] = mapped_column("cl_17c", String, ForeignKey("tb_0.cl_0a", ondelete="CASCADE"), nullable=False)
    content: Mapped[str] = mapped_column("cl_17d", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    status: Mapped[int] = mapped_column("cl_17e", Integer, nullable=False)
    removed_at: Mapped[Optional[datetime.datetime]] = mapped_column("cl_17f", DateTime, nullable=True)
