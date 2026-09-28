from domain.entities.reportEvidence import ReportEvidence
from core.errorUtils import excLocation
from infrastructure.database.models.reportEvidenceModel import ReportEvidenceModel
from infrastructure.database.models.reportModel import ReportModel
from exceptions.baseExceptions import NoHarmException
from security.encryption import Encryption

from core.database import Database
from core.config import config

from datetime import datetime, timedelta, timezone


class ReportEvidenceRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine


    def _toEntity(self, model: ReportEvidenceModel) -> ReportEvidence:
        return ReportEvidence(
            id=model.id,
            report=model.report,
            kind=model.kind,
            source_id=model.source_id,
            author_id=model.author_id,
            content=model.content,
            content_hash=model.content_hash,
            occurred_at=model.occurred_at,
            created_at=model.created_at,
            updated_at=model.updated_at
        )


    def createMany(self, items: list[ReportEvidence]) -> list[ReportEvidence]:
        """Store a batch of captured items, in one transaction.

        The hash is computed here rather than taken from the caller: evidence
        that reached the table without one would be indistinguishable from
        evidence that was edited afterwards, which is the single property this
        table exists to provide.

        All or nothing — a report whose evidence is half-written is worse than
        one with none, because the gap is invisible to whoever reads it later.
        """
        if not items:
            return []

        try:
            models = [
                ReportEvidenceModel(
                    report=item.report,
                    kind=item.kind,
                    source_id=item.source_id,
                    author_id=item.author_id,
                    content=item.content,
                    content_hash=Encryption.hash(item.content),
                    occurred_at=item.occurred_at
                )
                for item in items
            ]

            self.session.add_all(models)
            self.session.commit()

            return [self._toEntity(model) for model in models]
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findByReport(self, reportId) -> list[ReportEvidence]:
        """Everything captured for one report, oldest first.

        Order is the order it was said, not the order it was stored: a
        conversation read out of sequence is not evidence of anything.
        """
        try:
            models = self.session.query(ReportEvidenceModel).filter(
                ReportEvidenceModel.report == reportId
            ).order_by(
                ReportEvidenceModel.occurred_at.asc().nullsfirst(),
                ReportEvidenceModel.created_at.asc()
            ).all()

            return [self._toEntity(model) for model in models]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def countByReport(self, reportId) -> int:
        """How many items back a report — shown in the queue before opening it."""
        try:
            return self.session.query(ReportEvidenceModel).filter(
                ReportEvidenceModel.report == reportId
            ).count()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def countExpired(self, retentionDays: int) -> int:
        """Evidence past its retention window and still stored.

        The read-only half of `deleteExpired`, for the board. Non-zero means
        `purge-evidence` has stopped running, and what is sitting there is
        copied private messages kept past the purpose that justified copying
        them — the one retention failure in this system with a person on the
        other end of it.
        """
        try:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retentionDays)
            resolved = [config.STATUS_CODES["accepted"], config.STATUS_CODES["ignored"]]

            return (
                self.session.query(ReportEvidenceModel.id)
                .join(ReportModel, ReportModel.id == ReportEvidenceModel.report)
                .filter(
                    ReportModel.status.in_(resolved),
                    ReportModel.updated_at < cutoff,
                )
                .count()
            )
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def deleteExpired(self, retentionDays: int) -> int:
        """Drop the evidence behind reports resolved longer than `retentionDays` ago.

        The report itself stays — a moderator needs the history of what was
        decided about an account. What goes is the copied prose: private
        messages kept past the purpose that justified copying them are a
        liability, not a record.

        An open report is never touched, however old: it has not been read yet.
        """
        try:
            cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retentionDays)
            resolved = [config.STATUS_CODES["accepted"], config.STATUS_CODES["ignored"]]

            expired = self.session.query(ReportEvidenceModel.id).join(
                ReportModel, ReportModel.id == ReportEvidenceModel.report
            ).filter(
                ReportModel.status.in_(resolved),
                ReportModel.updated_at < cutoff
            ).all()

            ids = [row[0] for row in expired]
            if not ids:
                return 0

            deleted = self.session.query(ReportEvidenceModel).filter(
                ReportEvidenceModel.id.in_(ids)
            ).delete(synchronize_session=False)
            self.session.commit()

            return deleted
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
