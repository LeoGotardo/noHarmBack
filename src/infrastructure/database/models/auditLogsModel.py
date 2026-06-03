from typing import Optional
from sqlalchemy import Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig

import uuid


class AuditLogsModel(Base, TimestampMixin):
    __tablename__ = "tb_7"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_7a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[int] = mapped_column("cl_7b", Integer, nullable=False)
    catalyst_id: Mapped[Optional[uuid.UUID]] = mapped_column("cl_7c", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=True)
    catalyst: Mapped[Optional[int]] = mapped_column("cl_7d", Integer, nullable=True)
    description: Mapped[str] = mapped_column("cl_7e", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
