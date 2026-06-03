from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import uuid
import datetime


class UserBadgesModel(Base, TimestampMixin):
    __tablename__ = "tb_6"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_6a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column("cl_6b", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    badge_id: Mapped[uuid.UUID] = mapped_column("cl_6c", UUID(as_uuid=True), ForeignKey("tb_5.cl_5a"), nullable=False)
    given_at: Mapped[datetime.datetime] = mapped_column("cl_6d", StringEncryptedType(DateTime, _encryption_key, AesGcmEngine, 'pkcs5'), default=lambda: datetime.datetime.now(), nullable=False)
    status: Mapped[int] = mapped_column("cl_6e", Integer, nullable=False)
