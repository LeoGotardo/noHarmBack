from typing import Optional
from sqlalchemy import Integer, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import uuid
import datetime


class FriendshipModel(Base, TimestampMixin):
    __tablename__ = "tb_2"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_2a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender: Mapped[str] = mapped_column("cl_2b", String, ForeignKey("tb_0.cl_0a"), nullable=False)
    reciver: Mapped[str] = mapped_column("cl_2c", String, ForeignKey("tb_0.cl_0a"), nullable=False)
    status: Mapped[int] = mapped_column("cl_2f", Integer, nullable=False)
    # Who put the block on. Only they may lift it — without this, `unblock`
    # accepted either participant, the blocked one included (migration
    # 20261001_01). NULL for rows blocked before the column existed, and for
    # every row that is not blocked.
    blocked_by: Mapped[Optional[str]] = mapped_column("cl_2g", String, ForeignKey("tb_0.cl_0a", ondelete="SET NULL"), nullable=True)
