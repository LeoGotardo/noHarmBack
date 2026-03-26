from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property, Comparator
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin
from hashlib import sha256

import uuid
import datetime


class FriendshipModel(Base, TimestampMixin):
    __tablename__ = "tb_2"

    id = Column("cl_2a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender = Column("cl_2b", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    reciver = Column("cl_2c", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    _send_at_encrypted = Column("cl_2d", DateTime, nullable=False)
    _send_at_hash = Column("cl_2d_h", String(64), nullable=False, index=True)
    _recived_at_encrypted = Column("cl_2e", DateTime, nullable=False)
    _recived_at_hash = Column("cl_2e_h", String(64), nullable=False, index=True)
    status = Column("cl_2f", Integer, nullable=False)

    # ── send_at ───────────────────────────────────────────────────────────────

    @hybrid_property
    def send_at(self):
        if self._send_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._send_at_encrypted, key)
                if success:
                    return datetime.datetime.fromisoformat(decrypted)
        return None

    @send_at.setter
    def send_at(self, value: datetime.datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._send_at_encrypted = encrypted
                self._send_at_hash = Encryption.hash(value.isoformat())

    @send_at.expression
    def send_at(cls):
        return cls._send_at_hash

    @send_at.comparator
    class send_at(Comparator):
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

    # ── recived_at ────────────────────────────────────────────────────────────

    @hybrid_property
    def recived_at(self):
        if self._recived_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._recived_at_encrypted, key)
                if success:
                    return datetime.datetime.fromisoformat(decrypted)
        return None

    @recived_at.setter
    def recived_at(self, value: datetime.datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._recived_at_encrypted = encrypted
                self._recived_at_hash = Encryption.hash(value.isoformat())

    @recived_at.expression
    def recived_at(cls):
        return cls._recived_at_hash

    @recived_at.comparator
    class recived_at(Comparator):
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