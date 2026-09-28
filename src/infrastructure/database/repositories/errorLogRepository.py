from core.errorUtils import excLocation
from infrastructure.database.models.errorLogModel import ErrorLogModel
from domain.entities.errorLog import ErrorLog
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse
from core.database import Database

from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, timezone
from typing import Optional


def _utcNow() -> datetime:
    """Now, as the naive UTC the schema stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ErrorLogRepository:
    """Reads and writes `tb_14`, one row per distinct fault.

    `record` is an upsert on the fingerprint, written as select-then-write
    rather than `ON CONFLICT`: the message and traceback columns are encrypted
    types, and keeping the write on the ORM path is what guarantees they are
    encrypted on the way in. Two workers racing the same new fault collide on
    the unique index, which is caught and turned into the update it should have
    been.
    """

    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine

    def _toEntity(self, model: ErrorLogModel) -> ErrorLog:
        return ErrorLog(
            id=model.id,
            kind=model.kind,
            path=model.path,
            method=model.method,
            fingerprint=model.fingerprint,
            exception_type=model.exception_type,
            status_code=model.status_code,
            last_seen=model.last_seen,
            count=model.count,
            message=model.message,
            traceback=model.traceback,
            user_id=model.user_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def record(self, entry: ErrorLog) -> Optional[ErrorLog]:
        """Add a fault, or bump the one that matches its fingerprint.

        Returns None on any failure. This is called from the exception
        handlers, where raising would replace the error the user is about to be
        told about with a different one — see `ErrorLogService.capture`.
        """
        try:
            existing = (
                self.session.query(ErrorLogModel)
                .filter(ErrorLogModel.fingerprint == entry.fingerprint)
                .first()
            )

            if existing is not None:
                existing.count = (existing.count or 0) + 1
                existing.last_seen = entry.last_seen or _utcNow()
                # The newest occurrence's detail, not the first: when a fault
                # changes shape slightly the recent one is the one being
                # debugged.
                existing.message = entry.message
                existing.traceback = entry.traceback
                existing.status_code = entry.status_code
                existing.path = entry.path
                existing.method = entry.method
                existing.user_id = entry.user_id
                self.session.commit()
                return self._toEntity(existing)

            model = ErrorLogModel(
                kind=entry.kind,
                path=entry.path[:512],
                method=entry.method[:8],
                fingerprint=entry.fingerprint,
                exception_type=entry.exception_type[:128],
                status_code=entry.status_code,
                last_seen=entry.last_seen or _utcNow(),
                count=1,
                message=entry.message,
                traceback=entry.traceback,
                user_id=entry.user_id,
            )
            self.session.add(model)
            self.session.commit()
            return self._toEntity(model)

        except IntegrityError:
            # Another worker inserted the same new fault a moment ago. Retry as
            # the update it should have been; give up quietly if that fails too.
            self.session.rollback()
            try:
                existing = (
                    self.session.query(ErrorLogModel)
                    .filter(ErrorLogModel.fingerprint == entry.fingerprint)
                    .first()
                )
                if existing is None:
                    return None
                existing.count = (existing.count or 0) + 1
                existing.last_seen = entry.last_seen or _utcNow()
                self.session.commit()
                return self._toEntity(existing)
            except Exception:
                self.session.rollback()
                return None
        except Exception:
            self.session.rollback()
            return None

    def findRecent(self, params: Optional[PaginationParams] = None) -> list[ErrorLog] | PaginatedResponse[ErrorLog]:
        """Faults, most recently seen first — the only order the panel uses."""
        try:
            query = self.session.query(ErrorLogModel).order_by(ErrorLogModel.last_seen.desc())

            if params:
                total = query.count()
                offset = (params.page - 1) * params.pageSize
                rows = query.offset(offset).limit(params.pageSize).all()
                return createPaginatedResponse(
                    [self._toEntity(r) for r in rows], total, params.page, params.pageSize
                )

            return [self._toEntity(r) for r in query.all()]
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def countSince(self, since: datetime) -> int:
        """How many *occurrences* since an instant, not how many rows."""
        try:
            rows = (
                self.session.query(ErrorLogModel.count)
                .filter(ErrorLogModel.last_seen >= since)
                .all()
            )
            return sum(r[0] or 0 for r in rows)
        except Exception as e:
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def purgeOlderThan(self, days: int) -> int:
        """Drop faults nothing has hit in `days`. Returns how many went."""
        try:
            cutoff = _utcNow() - timedelta(days=days)
            deleted = (
                self.session.query(ErrorLogModel)
                .filter(ErrorLogModel.last_seen < cutoff)
                .delete(synchronize_session=False)
            )
            self.session.commit()
            return int(deleted or 0)
        except Exception as e:
            self.session.rollback()
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
