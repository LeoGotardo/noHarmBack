from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin

import uuid, datetime

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

    @hybrid_property
    def message(self):
        if self._message_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._message_encrypted, key)
                if success == True:
                    return decrypted
        return None

    @message.setter
    def message(self, value):
        if value:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response == True:
                success, encrypted = Encryption.encrypt(value, key)
                if success == True:
                    self._message_encrypted = encrypted 
                    self._message_hash = Encryption.hash(value)
                    
    @hybrid_property
    def send_at(self):
        if self._send_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._send_at_encrypted, key)
                if success == True:
                    return datetime.fromisoformat(decrypted)
        return None

    @send_at.setter
    def send_at(self, value: datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._send_at_encrypted = encrypted

    @hybrid_property
    def recived_at(self):
        if self._recived_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._recived_at_encrypted, key)
                if success == True:
                    return datetime.fromisoformat(decrypted)
        return None

    @recived_at.setter
    def recived_at(self, value: datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success: 
                self._recived_at_encrypted = encrypted