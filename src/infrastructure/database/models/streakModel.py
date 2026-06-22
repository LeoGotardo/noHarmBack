from typing import Optional
from sqlalchemy import DateTime, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import uuid
import datetime


class StreakModel(Base, TimestampMixin):
    __tablename__ = "tb_1"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_1a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column("cl_1b", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    start_at: Mapped[datetime.datetime] = mapped_column("cl_1c", StringEncryptedType(DateTime, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    end_at: Mapped[Optional[datetime.datetime]] = mapped_column("cl_1d", StringEncryptedType(DateTime, _encryption_key, AesGcmEngine, 'pkcs5'))
    status: Mapped[int] = mapped_column("cl_1e", Integer, nullable=False)
    is_record: Mapped[bool] = mapped_column("cl_1f", Boolean, nullable=False)
    last_checkin: Mapped[Optional[datetime.datetime]] = mapped_column("cl_1g", StringEncryptedType(DateTime, _encryption_key, AesGcmEngine, 'pkcs5'))
