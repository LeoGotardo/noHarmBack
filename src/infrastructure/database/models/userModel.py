from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import relationship, validates, Mapped, mapped_column
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from sqlalchemy_utils import StringEncryptedType
from core.config import config as appConfig
from security.encryption import Encryption


class UserModel(Base, TimestampMixin):
    __tablename__ = "tb_0"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[str] = mapped_column("cl_0a", String, primary_key=True)
    username: Mapped[str] = mapped_column("cl_0b", StringEncryptedType(String, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    username_hash: Mapped[str] = mapped_column("cl_0b_h", String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column("cl_0c", StringEncryptedType(String, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    email_hash: Mapped[str] = mapped_column("cl_0c_h", String(64), nullable=False, unique=True)
    profile_picture: Mapped[Optional[str]] = mapped_column("cl_0d", StringEncryptedType(String, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=True)
    status: Mapped[int] = mapped_column("cl_0e", Integer, nullable=False)
    # When the user asked for deletion. `updated_at` cannot stand in for this:
    # it carries onupdate, so any later write to the row would move the purge
    # deadline. NULL for every account that has not been deleted, and cleared
    # again when one is restored within the grace window.
    deleted_at: Mapped[Optional[datetime]] = mapped_column("cl_0f", DateTime, nullable=True)
    user_badges = relationship("UserBadgesModel", foreign_keys="UserBadgesModel.user_id")

    @validates('username')
    def _hash_username(self, key, value):
        self.username_hash = Encryption.hash(value)
        return value

    @validates('email')
    def _hash_email(self, key, value):
        self.email_hash = Encryption.hash(value)
        return value
