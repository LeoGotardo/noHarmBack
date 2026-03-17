from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from external.storageService import Base
from core.config import Config

import uuid, datetime

class FriendshipModel(Base):
    __tablename__ = "tb_2"
    
    id = Column("cl_2a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sender = Column("cl_2b", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    reciver = Column("cl_2c", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    _send_at_encrypted = Column("cl_2d", DateTime, nullable=False)
    _send_at_hash = Column("cl_2d_h", String(64), nullable=False, index=True)
    _recived_at_encrypted = Column("cl_2e", DateTime, nullable=False)
    _recived_at_hash = Column("cl_2e_h", String(64), nullable=False, index=True)
    status = Column("cl_2f", Integer, nullable=False)
    _created_at = Column("cl_2f", DateTime, nullable=False)
    _updated_at = Column("cl_2g", DateTime, nullable=False)
    
    
    @hybrid_property
    def send_at(self):
        if self._send_at_encrypted:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._send_at_encrypted, key)
                if success == True:
                    return datetime.fromisoformat(decrypted)
        return None

    @send_at.setter
    def send_at(self, value: datetime):
        if value:
            _, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success:
                self._send_at_encrypted = encrypted

    @hybrid_property
    def recived_at(self):
        if self._recived_at_encrypted:
            response, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._recived_at_encrypted, key)
                if success == True:
                    return datetime.fromisoformat(decrypted)
        return None

    @recived_at.setter
    def recived_at(self, value: datetime):
        if value:
            _, key = Encryption.keyGenerator(Config.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success: 
                self._recived_at_encrypted = encrypted