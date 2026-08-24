from typing import Optional
from sqlalchemy import Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import uuid
import datetime


class BadgeModel(Base, TimestampMixin):
    __tablename__ = "tb_5"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_5a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column("cl_5b", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    description: Mapped[str] = mapped_column("cl_5c", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    # Number of clean days the streak must reach, not a calendar date — two users
    # who started in different months share the same milestone (§8).
    milestone: Mapped[int] = mapped_column("cl_5d", Integer, nullable=False)
    icon: Mapped[str] = mapped_column("cl_5e", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    status: Mapped[int] = mapped_column("cl_5f", Integer, nullable=False)
