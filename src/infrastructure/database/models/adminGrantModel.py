from typing import Optional
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin


class AdminGrantModel(Base, TimestampMixin):
    """An account an official account promoted to administrator (tb_19).

    The other source is the `ADMIN_USER_IDS` allowlist, which this table does
    not replace: the environment is how the first administrator exists, and
    what it grants cannot be revoked from the app. See core/roles.py.

    `created_at` is when the promotion happened.
    """
    __tablename__ = "tb_19"

    user_id: Mapped[str] = mapped_column("cl_19a", String, ForeignKey("tb_0.cl_0a", ondelete="CASCADE"), primary_key=True)
    # The official account that promoted them. No foreign key: who decided has
    # to outlive that account, the same as everywhere else in moderation.
    granted_by: Mapped[Optional[str]] = mapped_column("cl_19b", String, nullable=True)
