from sqlalchemy import Column, Integer, String, LargeBinary
from sqlalchemy.ext.hybrid import hybrid_property, Comparator
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from sqlalchemy.orm import relationship
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin
from hashlib import sha256

import uuid


class UserModel(Base, TimestampMixin):
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

    # ── username ──────────────────────────────────────────────────────────────

    @hybrid_property
    def username(self):
        if self._username_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._username_encrypted, key)
                if success:
                    return decrypted
        return None

    @username.setter
    def username(self, value):
        if value:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, encrypted = Encryption.encrypt(value, key)
                if success:
                    self._username_encrypted = encrypted
                    self._username_hash = Encryption.hash(value)

    @username.expression
    def username(cls):
        return cls._username_hash

    @username.comparator
    class username(Comparator):
        def __eq__(self, other):
            if other is None:
                return self.__clause_element__().is_(None)
            return self.__clause_element__() == sha256(other.encode("utf-8")).hexdigest()

        def __ne__(self, other):
            if other is None:
                return self.__clause_element__().isnot(None)
            return self.__clause_element__() != sha256(other.encode("utf-8")).hexdigest()

    # ── email ─────────────────────────────────────────────────────────────────

    @hybrid_property
    def email(self):
        if self._email_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._email_encrypted, key)
                if success:
                    return decrypted
        return None

    @email.setter
    def email(self, value):
        if value:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, encrypted = Encryption.encrypt(value, key)
                if success:
                    self._email_encrypted = encrypted
                    self._email_hash = Encryption.hash(value)

    @email.expression
    def email(cls):
        return cls._email_hash

    @email.comparator
    class email(Comparator):
        def __eq__(self, other):
            if other is None:
                return self.__clause_element__().is_(None)
            return self.__clause_element__() == sha256(other.encode("utf-8")).hexdigest()

        def __ne__(self, other):
            if other is None:
                return self.__clause_element__().isnot(None)
            return self.__clause_element__() != sha256(other.encode("utf-8")).hexdigest()

    # ── profile_picture ───────────────────────────────────────────────────────

    @hybrid_property
    def profile_picture(self):
        if self._profile_picture_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, decrypted = Encryption.decrypt(self._profile_picture_encrypted, key)
                if success:
                    return decrypted
        return None

    @profile_picture.setter
    def profile_picture(self, value):
        if value:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response:
                success, encrypted = Encryption.encrypt(value, key)
                if success:
                    self._profile_picture_encrypted = encrypted
                    self._profile_picture_hash = Encryption.hash(value)

    @profile_picture.expression
    def profile_picture(cls):
        return cls._profile_picture_hash

    @profile_picture.comparator
    class profile_picture(Comparator):
        def __eq__(self, other):
            if other is None:
                return self.__clause_element__().is_(None)
            return self.__clause_element__() == sha256(other.encode("utf-8")).hexdigest()

        def __ne__(self, other):
            if other is None:
                return self.__clause_element__().isnot(None)
            return self.__clause_element__() != sha256(other.encode("utf-8")).hexdigest()