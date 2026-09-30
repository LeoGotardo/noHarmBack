from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import _utcnow

import uuid


class PostLikeModel(Base):
    """One user liking one post (tb_18).

    The composite primary key is the whole design: it is what makes
    `PUT /posts/{id}/like` idempotent, because a second INSERT of the same pair
    is `ON CONFLICT DO NOTHING` rather than a second like. No `updated_at` — a
    like has no second state.
    """
    __tablename__ = "tb_18"

    post_id: Mapped[uuid.UUID] = mapped_column("cl_18a", UUID(as_uuid=True), ForeignKey("tb_16.cl_16a", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column("cl_18b", String, ForeignKey("tb_0.cl_0a", ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime, nullable=False, default=_utcnow)
