from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.dialects.postgresql import UUID
from security.encryption import Encryption
from infrastructure.external.storageService import Base
from core.config import config as appConfig
from infrastructure.database.models.baseModel import TimestampMixin

import uuid, datetime

class UserBadgesModel(Base, TimestampMixin):
    __tablename__ = "tb_6"
    
    id = Column("cl_6a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column("cl_6b", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False)
    badge_id = Column("cl_6c", UUID(as_uuid=True), ForeignKey("tb_1.cl_1a"), nullable=False)
    _given_at_encrypted = Column("cl_6d", DateTime, nullable=False)
    _given_at_hash = Column("cl_6d_h", String(64), nullable=False, index=True)
    status = Column("cl_6e", Integer, nullable=False)
    
    @hybrid_property
    def given_at(self):
        if self._given_at_encrypted:
            response, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            if response == True:
                success, decrypted = Encryption.decrypt(self._given_at_encrypted, key)
                if success == True:
                    return datetime.fromisoformat(decrypted)
        return None

    @given_at.setter
    def given_at(self, value: datetime):
        if value:
            _, key = Encryption.keyGenerator(appConfig.ENCRYPTION_KEY)
            success, encrypted = Encryption.encrypt(value.isoformat(), key)
            if success: 
                self._given_at_encrypted = encrypted