from typing import Optional
from sqlalchemy import Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import uuid
import datetime


class ChatModel(Base, TimestampMixin):
    __tablename__ = "tb_3"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_3a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender: Mapped[uuid.UUID] = mapped_column("cl_3b", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    reciver: Mapped[uuid.UUID] = mapped_column("cl_3c", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column("cl_3d", StringEncryptedType(DateTime, _encryption_key, AesGcmEngine, 'pkcs5'), default=lambda: datetime.datetime.now(), nullable=False)
    ended_at: Mapped[Optional[datetime.datetime]] = mapped_column("cl_3e", StringEncryptedType(DateTime, _encryption_key, AesGcmEngine, 'pkcs5'))
    status: Mapped[int] = mapped_column("cl_3f", Integer, nullable=False)
    messages = relationship("MessageModel", foreign_keys="MessageModel.chat")
