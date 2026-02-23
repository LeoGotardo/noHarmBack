from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.orm import relationship
from external.storageService import Base
from sqlalchemy.dialects.postgresql import UUID
import uuid

class UserModel(Base):
    __tablename__ = "tb_0"
    id = Column("cl_0a", String(255), primary_key=True, default=uuid.uuid4)
    username = Column("cl_0b", String(50), nullable=False)