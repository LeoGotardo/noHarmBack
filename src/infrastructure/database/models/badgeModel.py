from sqlalchemy import Column, Integer, String, DateTime, LargeBinary, Text
from sqlalchemy.ext.hybrid import hybrid_property, Comparator
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin
from hashlib import sha256

import uuid
import datetime


class BadgeModel(Base, TimestampMixin):
    __tablename__ = "tb_5"

    id = Column("cl_5a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    _name_encrypted = Column("cl_5b", String(500), nullable=False)
    _name_hash = Column("cl_5b_h", String(64), nullable=False, index=True)
    _description_encrypted = Column("cl_5c", Text, nullable=False)
    _description_hash = Column("cl_5c_h", String(64), nullable=False, index=True)
    _milestone_encrypted = Column("cl_5d", DateTime, nullable=False)
    _milestone_hash = Column("cl_5d_h", String(64), nullable=False, index=True)
    _icon_encrypted = Column("cl_5e", LargeBinary, nullable=False)
    _icon_hash = Column("cl_5e_h", String(64), nullable=False, index=True)
    status = Column("cl_5f", Integer, nullable=False)

    # ── name ──────────────────────────────────────────────────────────────────

    @hybrid_property
    def name(self):
        if self._name_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._name_encrypted, key)
                if success:
                    return decrypted
        return None

    @name.setter
    def name(self, value):
        if value:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, encrypted = Encryption.encrypt(value, key)
                if success:
                    self._name_encrypted = encrypted
                    self._name_hash = Encryption.hash(value)

    @name.expression
    def name(cls):
        return cls._name_hash

    @name.comparator
    class name(Comparator):
        def __eq__(self, other):
            if other is None:
                return self.__clause_element__().is_(None)
            return self.__clause_element__() == sha256(other.encode("utf-8")).hexdigest()

        def __ne__(self, other):
            if other is None:
                return self.__clause_element__().isnot(None)
            return self.__clause_element__() != sha256(other.encode("utf-8")).hexdigest()

    # ── description ───────────────────────────────────────────────────────────

    @hybrid_property
    def description(self):
        if self._description_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._description_encrypted, key)
                if success:
                    return decrypted
        return None

    @description.setter
    def description(self, value):
        if value:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, encrypted = Encryption.encrypt(value, key)
                if success:
                    self._description_encrypted = encrypted
                    self._description_hash = Encryption.hash(value)

    @description.expression
    def description(cls):
        return cls._description_hash

    @description.comparator
    class description(Comparator):
        def __eq__(self, other):
            if other is None:
                return self.__clause_element__().is_(None)
            return self.__clause_element__() == sha256(other.encode("utf-8")).hexdigest()

        def __ne__(self, other):
            if other is None:
                return self.__clause_element__().isnot(None)
            return self.__clause_element__() != sha256(other.encode("utf-8")).hexdigest()

    # ── milestone ─────────────────────────────────────────────────────────────

    @hybrid_property
    def milestone(self):
        if self._milestone_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._milestone_encrypted, key)
                if success:
                    return datetime.datetime.fromisoformat(decrypted)
        return None

    @milestone.setter
    def milestone(self, value: datetime.datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._milestone_encrypted = encrypted
                self._milestone_hash = Encryption.hash(value.isoformat())

    @milestone.expression
    def milestone(cls):
        return cls._milestone_hash

    @milestone.comparator
    class milestone(Comparator):
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

    # ── icon ──────────────────────────────────────────────────────────────────

    @hybrid_property
    def icon(self):
        if self._icon_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._icon_encrypted, key)
                if success:
                    return decrypted
        return None

    @icon.setter
    def icon(self, value):
        if value:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, encrypted = Encryption.encrypt(value, key)
                if success:
                    self._icon_encrypted = encrypted
                    self._icon_hash = Encryption.hash(value)

    @icon.expression
    def icon(cls):
        return cls._icon_hash

    @icon.comparator
    class icon(Comparator):
        def __eq__(self, other):
            if other is None:
                return self.__clause_element__().is_(None)
            val = other if isinstance(other, str) else str(other)
            return self.__clause_element__() == sha256(val.encode("utf-8")).hexdigest()

        def __ne__(self, other):
            if other is None:
                return self.__clause_element__().isnot(None)
            val = other if isinstance(other, str) else str(other)
            return self.__clause_element__() != sha256(val.encode("utf-8")).hexdigest()