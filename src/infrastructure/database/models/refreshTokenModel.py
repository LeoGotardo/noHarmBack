from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin

import uuid


class RefreshTokenModel(Base, TimestampMixin):
    """Persisted refresh tokens (§2.2).

    Stores a SHA-256 hash of the raw JWT so the plaintext token is never
    written to disk.  On rotation the old row is deleted and a new one is
    inserted, enforcing single-use semantics.
    """
    __tablename__ = "tb_8"

    id         = Column("cl_8a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column("cl_8b", UUID(as_uuid=True), ForeignKey("tb_0.cl_0a"), nullable=False, index=True)
    token_hash = Column("cl_8c", Text, nullable=False, unique=True)
    expires_at = Column("cl_8d", DateTime, nullable=False)
    device_hint = Column("cl_8e", Text, nullable=True)
