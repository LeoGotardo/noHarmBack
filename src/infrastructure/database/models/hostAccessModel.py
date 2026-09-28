from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin

import datetime
import uuid


class HostAccessModel(Base, TimestampMixin):
    """Someone logged into the machine (tb_15).

    Written by a script on the host rather than by the application: `auth.log`
    lives outside the container, and mounting a root-owned file that records
    every login on the box into the app process is a wider grant than this
    needs.

    Nothing here is encrypted. An OS user name and a source address are facts
    about the server, not about any account — and they are what a reader
    filters on.

    **This is not proof.** Anyone with root can edit `auth.log` before the
    script reads it. It catches access nobody expected and carelessness; it
    does not catch an attacker who is covering their tracks, and reading it as
    if it did is worse than not having it.
    """

    __tablename__ = "tb_15"

    id: Mapped[uuid.UUID] = mapped_column("cl_15a", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurred_at: Mapped[datetime.datetime] = mapped_column("cl_15b", DateTime, nullable=False)
    os_user: Mapped[str] = mapped_column("cl_15c", String(64), nullable=False)
    source_ip: Mapped[str] = mapped_column("cl_15d", String(64), nullable=False)
    method: Mapped[str] = mapped_column("cl_15e", String(32), nullable=False)
    result: Mapped[str] = mapped_column("cl_15f", String(16), nullable=False)
