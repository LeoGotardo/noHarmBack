from datetime import date, datetime
from typing import Optional
from sqlalchemy import Boolean, Date, DateTime, Integer, String
from sqlalchemy.orm import relationship, validates, Mapped, mapped_column
from infrastructure.external.storageService import Base
from infrastructure.database.models.baseModel import TimestampMixin
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine
from sqlalchemy_utils import StringEncryptedType
from core.config import config as appConfig
from security.encryption import Encryption


class UserModel(Base, TimestampMixin):
    __tablename__ = "tb_0"

    _encryption_key = appConfig.DATABASE_ENCRYPTION_KEY

    id: Mapped[str] = mapped_column("cl_0a", String, primary_key=True)
    username: Mapped[str] = mapped_column("cl_0b", StringEncryptedType(String, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    username_hash: Mapped[str] = mapped_column("cl_0b_h", String(64), nullable=False, unique=True)
    email: Mapped[str] = mapped_column("cl_0c", StringEncryptedType(String, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=False)
    email_hash: Mapped[str] = mapped_column("cl_0c_h", String(64), nullable=False, unique=True)
    profile_picture: Mapped[Optional[str]] = mapped_column("cl_0d", StringEncryptedType(String, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=True)
    status: Mapped[int] = mapped_column("cl_0e", Integer, nullable=False)
    # When the user asked for deletion. `updated_at` cannot stand in for this:
    # it carries onupdate, so any later write to the row would move the purge
    # deadline. NULL for every account that has not been deleted, and cleared
    # again when one is restored within the grace window.
    deleted_at: Mapped[Optional[datetime]] = mapped_column("cl_0f", DateTime, nullable=True)
    # When a suspension ends. NULL covers both "not banned" and "banned for
    # good": a status of `banned` with no date is permanent, which is what the
    # column meant before this existed. A timed suspension is the same status
    # plus an instant, and it lifts itself at the next sign-in — see
    # `AuthService._liftExpiredSuspension`. Nothing sweeps it on a schedule,
    # because an account nobody is trying to use does not need unbanning.
    banned_until: Mapped[Optional[datetime]] = mapped_column("cl_0g", DateTime, nullable=True)
    # The account must pick a new username before it can be used. Moderation
    # sets it together with a rename to a neutral handle — the flag is what
    # makes the app insist on a real one, not what hides the old name. See
    # migration 20260916_01.
    must_change_username: Mapped[bool] = mapped_column("cl_0h", Boolean, nullable=False, default=False, server_default="false")
    # The account's picture is blocked. Not the same as "has none": `cl_0d` is
    # nulled with it, and this is what stops the Google claim putting it back
    # at the next login (`AuthService._syncProfilePicture`).
    picture_blocked: Mapped[bool] = mapped_column("cl_0i", Boolean, nullable=False, default=False, server_default="false")
    # Declared at registration and checked against MINIMUM_AGE_YEARS. Encrypted
    # like every other personal field here, with no blind index: nothing ever
    # looks an account up by it.
    #
    # Nullable because every account created before the question existed has no
    # honest value to backfill. Registration requires it from here on; the
    # column staying nullable is what leaves "ask the existing accounts too"
    # available as a later decision rather than a migration that invents dates.
    birth_date: Mapped[Optional[date]] = mapped_column("cl_0j", StringEncryptedType(Date, _encryption_key, AesGcmEngine, 'pkcs5'), nullable=True)
    user_badges = relationship("UserBadgesModel", foreign_keys="UserBadgesModel.user_id")

    @validates('username')
    def _hash_username(self, key, value):
        self.username_hash = Encryption.hash(value)
        return value

    @validates('email')
    def _hash_email(self, key, value):
        self.email_hash = Encryption.hash(value)
        return value
