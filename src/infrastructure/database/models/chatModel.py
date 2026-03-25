from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from sqlalchemy.orm import relationship
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin

import uuid, datetime

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

    @hybrid_property
    def started_at(self):
        if self._started_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._started_at_encrypted, key)
                if success == True:
                    return datetime.fromisoformat(decrypted)
        return None

    @started_at.setter
    def started_at(self, value: datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._started_at_encrypted = encrypted

    @hybrid_property
    def ended_at(self):
        if self._ended_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._ended_at_encrypted, key)
                if success == True:
                    return datetime.fromisoformat(decrypted)
        return None

    @ended_at.setter
    def ended_at(self, value: datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success: 
                self._ended_at_encrypted = encrypted