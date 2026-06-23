from typing import Optional
from sqlalchemy import Integer, DateTime, Text, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import uuid
import datetime


class MessageModel(Base, TimestampMixin):
    __tablename__ = "tb_4"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_4a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat: Mapped[uuid.UUID] = mapped_column("cl_4b", UUID(as_uuid=True), ForeignKey("tb_3.cl_3a"), nullable=False)
    sender: Mapped[str] = mapped_column("cl_4c", String, ForeignKey("tb_0.cl_0a"), nullable=False)
    message: Mapped[str] = mapped_column("cl_4d", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    status: Mapped[int] = mapped_column("cl_4e", Integer, nullable=False)
    send_at: Mapped[datetime.datetime] = mapped_column("cl_4f", StringEncryptedType(DateTime, _encryption_key, AesGcmEngine, 'pkcs5'), default=lambda: datetime.datetime.now(), nullable=False)
    recived_at: Mapped[Optional[datetime.datetime]] = mapped_column("cl_4g", StringEncryptedType(DateTime, _encryption_key, AesGcmEngine, 'pkcs5'))
