from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property, Comparator
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from sqlalchemy.orm import relationship
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin
from hashlib import sha256

import uuid
import datetime


class ChatModel(Base, TimestampMixin):
    __tablename__ = "tb_3"

    id = Column("cl_3a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender = Column("cl_3b", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    reciver = Column("cl_3c", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    _started_at_encrypted = Column("cl_3d", DateTime, nullable=False)
    _started_at_hash = Column("cl_3d_h", String(64), nullable=False, index=True)
    _ended_at_encrypted = Column("cl_3e", DateTime, nullable=False)
    _ended_at_hash = Column("cl_3e_h", String(64), nullable=False, index=True)
    status = Column("cl_3f", Integer, nullable=False)
    messages = relationship("MessageModel", back_populates="chat")

    # ── started_at ────────────────────────────────────────────────────────────

    @hybrid_property
    def started_at(self):
        if self._started_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._started_at_encrypted, key)
                if success:
                    return datetime.datetime.fromisoformat(decrypted)
        return None

    @started_at.setter
    def started_at(self, value: datetime.datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._started_at_encrypted = encrypted
                self._started_at_hash = Encryption.hash(value.isoformat())

    @started_at.expression
    def started_at(cls):
        return cls._started_at_hash

    @started_at.comparator
    class started_at(Comparator):
        def __eq__(self, other):
            if other is None:
                return self.__clause_element__().is_(None)
            val = other.isoformat() if isinstance(other, datetime.datetime) else str(other)
            return self.__clause_element__() == sha256(val.encode("utf-8")).hexdigest()

        def __ne__(self, other):
            if other is None:
                return self.__clause_element__().isnot(None)
            val = other.isoformat() if isinstance(other, datetime.datetime) else str(other)
            return self.__clause_element__() != sha256(val.encode("utf-8")).hexdigest()

    # ── ended_at ──────────────────────────────────────────────────────────────

    @hybrid_property
    def ended_at(self):
        if self._ended_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._ended_at_encrypted, key)
                if success:
                    return datetime.datetime.fromisoformat(decrypted)
        return None

    @ended_at.setter
    def ended_at(self, value: datetime.datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._ended_at_encrypted = encrypted
                self._ended_at_hash = Encryption.hash(value.isoformat())

    @ended_at.expression
    def ended_at(cls):
        return cls._ended_at_hash

    @ended_at.comparator
    class ended_at(Comparator):
        def __eq__(self, other):
            if other is None:
                return self.__clause_element__().is_(None)
            val = other.isoformat() if isinstance(other, datetime.datetime) else str(other)
            return self.__clause_element__() == sha256(val.encode("utf-8")).hexdigest()

        def __ne__(self, other):
            if other is None:
                return self.__clause_element__().isnot(None)
            val = other.isoformat() if isinstance(other, datetime.datetime) else str(other)
            return self.__clause_element__() != sha256(val.encode("utf-8")).hexdigest()