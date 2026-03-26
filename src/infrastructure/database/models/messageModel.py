from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property, Comparator
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin
from hashlib import sha256

import uuid
import datetime


class MessageModel(Base, TimestampMixin):
    __tablename__ = "tb_4"

    id = Column("cl_4a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    chat = Column("cl_4b", UUID(as_uuid=True), ForeignKey("tb_3.cl_3a"), nullable=False)
    sender = Column("cl_4c", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    _message_encrypted = Column("cl_4d", Text, nullable=False)
    _message_hash = Column("cl_4d_h", String(64), nullable=False, index=True)
    status = Column("cl_4e", Integer, nullable=False)
    send_at_encrypted = Column("cl_4f", DateTime, nullable=False)
    send_at_hash = Column("cl_4f_h", String(64), nullable=False, index=True)
    recived_at_encrypted = Column("cl_4g", DateTime, nullable=False)
    recived_at_hash = Column("cl_4g_h", String(64), nullable=False, index=True)

    # ── message ───────────────────────────────────────────────────────────────

    @hybrid_property
    def message(self):
        if self._message_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._message_encrypted, key)
                if success:
                    return decrypted
        return None

    @message.setter
    def message(self, value):
        if value:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, encrypted = Encryption.encrypt(value, key)
                if success:
                    self._message_encrypted = encrypted
                    self._message_hash = Encryption.hash(value)

    @message.expression
    def message(cls):
        return cls._message_hash

    @message.comparator
    class message(Comparator):
        def __eq__(self, other):
            if other is None:
                return self.__clause_element__().is_(None)
            return self.__clause_element__() == sha256(other.encode("utf-8")).hexdigest()

        def __ne__(self, other):
            if other is None:
                return self.__clause_element__().isnot(None)
            return self.__clause_element__() != sha256(other.encode("utf-8")).hexdigest()

    # ── send_at ───────────────────────────────────────────────────────────────

    @hybrid_property
    def send_at(self):
        if self.send_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self.send_at_encrypted, key)
                if success:
                    return datetime.datetime.fromisoformat(decrypted)
        return None

    @send_at.setter
    def send_at(self, value: datetime.datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self.send_at_encrypted = encrypted
                self.send_at_hash = Encryption.hash(value.isoformat())

    @send_at.expression
    def send_at(cls):
        return cls.send_at_hash

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
        if self.recived_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self.recived_at_encrypted, key)
                if success:
                    return datetime.datetime.fromisoformat(decrypted)
        return None

    @recived_at.setter
    def recived_at(self, value: datetime.datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self.recived_at_encrypted = encrypted
                self.recived_at_hash = Encryption.hash(value.isoformat())

    @recived_at.expression
    def recived_at(cls):
        return cls.recived_at_hash

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