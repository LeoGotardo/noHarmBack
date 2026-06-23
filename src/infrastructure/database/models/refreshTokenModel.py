from typing import Optional
from sqlalchemy import Text, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin

import uuid
import datetime


class RefreshTokenModel(Base, TimestampMixin):
    __tablename__ = "tb_8"

    id: Mapped[uuid.UUID] = mapped_column("cl_8a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column("cl_8b", String, ForeignKey("tb_0.cl_0a"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column("cl_8c", Text, nullable=False, unique=True)
    expires_at: Mapped[datetime.datetime] = mapped_column("cl_8d", DateTime, nullable=False)
    device_hint: Mapped[Optional[str]] = mapped_column("cl_8e", Text, nullable=True)
