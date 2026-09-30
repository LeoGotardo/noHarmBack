from sqlalchemy import Boolean, Integer, Text, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from core.config import config as appConfig
from security.encryption import Encryption

import uuid


class NotificationModel(Base, TimestampMixin):
    __tablename__ = "tb_9"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[uuid.UUID] = mapped_column("cl_9a", PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column("cl_9b", String, ForeignKey("tb_0.cl_0a"), nullable=False)
    device_fcm: Mapped[str] = mapped_column("cl_9c", StringEncryptedType(Text, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    device_fcm_hash: Mapped[str] = mapped_column("cl_9c_h", String(64), nullable=False, index=True)
    status: Mapped[int] = mapped_column("cl_9d", Integer, nullable=False)
    # What this device asked to be woken up for — see migration 20260928_01.
    # Read by `fcmService.sendPushToUser`, which is the only place a push
    # category is decided.
    messages: Mapped[bool] = mapped_column("cl_9e", Boolean, nullable=False, default=True, server_default="true")
    friends: Mapped[bool] = mapped_column("cl_9f", Boolean, nullable=False, default=True, server_default="true")
    # A comment on one of your posts (migration 20261001_01).
    community: Mapped[bool] = mapped_column("cl_9g", Boolean, nullable=False, default=True, server_default="true")

    @validates('device_fcm')
    def _hash_device_fcm(self, _key, value):
        self.device_fcm_hash = Encryption.hash(value)
        return value
