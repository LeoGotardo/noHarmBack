from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean
from sqlalchemy.ext.hybrid import hybrid_property, Comparator
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin
from hashlib import sha256

import uuid
import datetime


class StreakModel(Base, TimestampMixin):
    __tablename__ = "tb_1"

    id = Column("cl_1a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column("cl_1b", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    _start_encrypted = Column("cl_1c", DateTime, nullable=False)
    _start_hash = Column("cl_1c_h", String(64), nullable=False, index=True)
    _end_encrypted = Column("cl_1d", DateTime, nullable=False)
    _end_hash = Column("cl_1d_h", String(64), nullable=False, index=True)
    status = Column("cl_1e", Integer, nullable=False)
    is_record = Column("cl_1f", Boolean, nullable=False)

    # ── start ─────────────────────────────────────────────────────────────────

    @hybrid_property
    def start(self):
        if self._start_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._start_encrypted, key)
                if success:
                    return datetime.datetime.fromisoformat(decrypted)
        return None

    @start.setter
    def start(self, value: datetime.datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._start_encrypted = encrypted
                self._start_hash = Encryption.hash(value.isoformat())

    @start.expression
    def start(cls):
        return cls._start_hash

    @start.comparator
    class start(Comparator):
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

    # ── end ───────────────────────────────────────────────────────────────────

    @hybrid_property
    def end(self):
        if self._end_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._end_encrypted, key)
                if success:
                    return datetime.datetime.fromisoformat(decrypted)
        return None

    @end.setter
    def end(self, value: datetime.datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._end_encrypted = encrypted
                self._end_hash = Encryption.hash(value.isoformat())

    @end.expression
    def end(cls):
        return cls._end_hash

    @end.comparator
    class end(Comparator):
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