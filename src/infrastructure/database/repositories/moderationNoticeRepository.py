from domain.entities.moderationNotice import ModerationNotice
from core.errorUtils import excLocation
from infrastructure.database.models.moderationNoticeModel import ModerationNoticeModel
from exceptions.baseExceptions import NoHarmException

from core.database import Database

from sqlalchemy import func

from datetime import datetime, timezone
from typing import Optional


class ModerationNoticeRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine


    def _toEntity(self, model: ModerationNoticeModel) -> ModerationNotice:
        return ModerationNotice(
            id=model.id,
            user_id=model.user_id,
            kind=model.kind,
            reason=model.reason,
            message=model.message,
            issued_by=model.issued_by,
            acknowledged_at=model.acknowledged_at,
            created_at=model.created_at,
            updated_at=model.updated_at
        )


    def create(self, notice: ModerationNotice) -> ModerationNotice:
        try:
            model = ModerationNoticeModel(
                user_id=notice.user_id,
                kind=notice.kind,
                reason=notice.reason,
                message=notice.message,
                issued_by=notice.issued_by
            )

            self.session.add(model)
            self.session.commit()

            return self._toEntity(model)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findById(self, id: str, returnModel: bool = False) -> ModerationNotice | ModerationNoticeModel:
        try:
            model = self.session.query(ModerationNoticeModel).filter(
                ModerationNoticeModel.id == id
            ).first()
            if model:
                return model if returnModel else self._toEntity(model)
            raise NoHarmException(statusCode=404, message="Notice not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findByUser(self, userId: str, unacknowledgedOnly: bool = False) -> list[ModerationNotice]:
        """A user's notices, oldest first.

        Oldest first on purpose: two notices waiting are a sequence — the
        warning that came before the suspension explains it.
        """
        try:
            query = self.session.query(ModerationNoticeModel).filter(
                ModerationNoticeModel.user_id == userId
            )
            if unacknowledgedOnly:
                query = query.filter(ModerationNoticeModel.acknowledged_at.is_(None))

            models = query.order_by(ModerationNoticeModel.created_at.asc()).all()
            return [self._toEntity(model) for model in models]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def acknowledge(self, id: str) -> ModerationNotice:
        """Stamp a notice as read. Idempotent: the first time is the one kept."""
        try:
            model = self.findById(id, returnModel=True)

            if model.acknowledged_at is None:
                model.acknowledged_at = datetime.now(timezone.utc).replace(tzinfo=None)
                self.session.commit()

            return self._toEntity(model)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def countsByKindSince(self, since: datetime) -> dict[str, int]:
        """What moderation has said lately, grouped by kind.

        Four kinds now — `warning`, `suspension`, `rename`, `picture` — and the
        split is the point: they are four different decisions, and a single
        "notices sent" total would read as one activity when the ladder's whole
        design is that they are not.
        """
        try:
            rows = (
                self.session.query(
                    ModerationNoticeModel.kind, func.count(ModerationNoticeModel.id)
                )
                .filter(ModerationNoticeModel.created_at >= since)
                .group_by(ModerationNoticeModel.kind)
                .all()
            )
            return {str(kind): int(total) for kind, total in rows}
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def countUnacknowledged(self) -> int:
        """Notices nobody has opened yet.

        Not a backlog anyone can clear: it drains when the accounts come back
        and read them. It rises when moderation is talking to people who have
        stopped signing in, which is worth knowing before sending more.
        """
        try:
            return (
                self.session.query(ModerationNoticeModel.id)
                .filter(ModerationNoticeModel.acknowledged_at.is_(None))
                .count()
            )
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def countWarnings(self, userId: str) -> int:
        """How many warnings this account has had — the ladder's own memory."""
        try:
            return self.session.query(ModerationNoticeModel).filter(
                ModerationNoticeModel.user_id == userId,
                ModerationNoticeModel.kind == "warning"
            ).count()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
