from sqlalchemy import Column, Integer, String, DateTime, LargeBinary, Text
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from external.storageService import Base
from core.config import Config

import uuid, datetime

class BadgeModel(Base):
    __tablename__ = "tb_1"
    
    id = Column("cl_5a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    _name_encrypted = Column("cl_5b", String(500), nullable=False)
    _name_hash = Column("cl_5b_h", String(64), nullable=False, index=True)
    _description_encrypted = Column("cl_5c", Text, nullable=False)
    _description_hash = Column("cl_5c_h", String(64), nullable=False, index=True)
    _milestone_encrypted = Column("cl_5d", DateTime, nullable=False)
    _milestone_hash = Column("cl_5d_h", String(64), nullable=False, index=True)
    _icon_encrypted = Column("cl_5e", LargeBinary, nullable=False)
    _icon_hash = Column("cl_5e_h", String(64), nullable=False, index=True)
    status = Column("cl_5e", Integer, nullable=False)
    created_at = Column("cl_5f", DateTime, nullable=False)
    updated_at = Column("cl_5g", DateTime, nullable=False)

    @hybrid_property
    def name(self):
        if self._name_encrypted:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._name_encrypted, key)
                if success == True:
                    return decrypted
        return None

    @name.setter
    def name(self, value):
        if value:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, encrypted = Encryption.encrypt(value, key)
                if success == True:
                    self._name_encrypted = encrypted
                    self._name_hash = Encryption.hash(value)

    @hybrid_property
    def description(self):
        if self._description_encrypted:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._description_encrypted, key)
                if success == True:
                    return decrypted
        return None

    @description.setter
    def description(self, value):
        if value:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, encrypted = Encryption.encrypt(value, key)
                if success == True:
                    self._description_encrypted = encrypted
                    self._description_hash = Encryption.hash(value)

    @hybrid_property
    def milestone(self):
        if self._milestone:
            _, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            success, decrypted = Encryption.decrypt(self._milestone, key)
            if success:
                return datetime.fromisoformat(decrypted)
        return None

    @milestone.setter
    def milestone(self, value: datetime):
        if value:
            _, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._milestone = encrypted
                
    @hybrid_property
    def icon(self):
        if self._icon_encrypted:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._icon_encrypted, key)
                if success == True:
                    return decrypted
                
    @icon.setter
    def icon(self, value):
        if value:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, encrypted = Encryption.encrypt(value, key)
                if success == True:
                    self._icon_encrypted = encrypted
                    self._icon_hash = Encryption.hash(value)