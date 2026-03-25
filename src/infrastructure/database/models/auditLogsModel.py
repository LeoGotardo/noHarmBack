from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin

import uuid

class AuditLogsModel(Base, TimestampMixin):
    __tablename__ = "tb_7"
    
    id = Column("cl_7a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type = Column("cl_7b", Integer, nullable=False)
    catalyst_id = Column("cl_7c", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=True)
    catalyst = Column("cl_7d",  Integer, nullable=True)
    _description_encrypted = Column("cl_7e", Text, nullable=False)

    @hybrid_property
    def description(self):
        if self._description_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._description_encrypted, key)
                if success == True:
                    return decrypted
        return None

    @description.setter
    def description(self, value):
        if value:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response == True:
                success, encrypted = Encryption.encrypt(value, key)
                if success == True:
                    self._description_encrypted = encrypted 
                    self._description_hash = Encryption.hash(value)