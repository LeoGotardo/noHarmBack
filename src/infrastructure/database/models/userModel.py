from sqlalchemy import Column, Integer, String, DateTime, LargeBinary
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from external.storageService import Base
from sqlalchemy.orm import relationship
from core.config import Config

import uuid

class UserModel(Base):
    __tablename__ = "tb_0"
    
    id = Column("cl_0a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    _username_encrypted = Column("cl_0b", String(500), nullable=False, unique=True)
    _username_hash = Column("cl_0b_h", String(64), nullable=False, unique=True, index=True)
    _email_encrypted = Column("cl_0c", String(500), nullable=False, unique=True)
    _email_hash = Column("cl_0c_h", String(64), nullable=False, unique=True, index=True)
    _profile_picture_encrypted = Column("cl_0d", LargeBinary, nullable=False)
    _profile_picture_hash = Column("cl_0d_h", String(64), nullable=False, index=True)
    status = Column("cl_0e", Integer, nullable=False)
    user_badges = relationship("UserBadgesModel", foreign_keys="UserBadgesModel.user_id")
    created_at = Column("cl_0f", DateTime, nullable=False)
    updated_at = Column("cl_0g", DateTime, nullable=False)

    @hybrid_property
    def username(self):
        if self._username_encrypted:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._username_encrypted, key)
                if success == True:
                    return decrypted
        return None

    @username.setter
    def username(self, value):
        if value:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, encrypted = Encryption.encrypt(value, key)
                if success == True:
                    self._username_encrypted = encrypted
                    self._username_hash = Encryption.hash(value)

    @hybrid_property
    def email(self):
        if self._email_encrypted:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._email_encrypted, key)
                if success == True:
                    return decrypted
        return None

    @email.setter
    def email(self, value):
        if value:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, encrypted = Encryption.encrypt(value, key)
                if success == True:
                    self._email_encrypted = encrypted
                    self._email_hash = Encryption.hash(value)