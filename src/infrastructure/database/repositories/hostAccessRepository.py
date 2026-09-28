from core.errorUtils import excLocation
from infrastructure.database.models.hostAccessModel import HostAccessModel
from domain.entities.errorLog import HostAccess
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse
from core.database import Database

from sqlalchemy.exc import IntegrityError
from typing import Optional


class HostAccessRepository:
    """Reads and writes `tb_15`.

    `record` is idempotent on the natural key (instant, address, user). The
    host script sends a window of the SSH log, and a window that overlaps the
    last one — because the cursor file was lost, or the script ran twice — must
    not double every login in it.
    """

    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine

    def _toEntity(self, model: HostAccessModel) -> HostAccess:
        return HostAccess(
            id=model.id,
            occurred_at=model.occurred_at,
            os_user=model.os_user,
            source_ip=model.source_ip,
            method=model.method,
            result=model.result,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def record(self, entry: HostAccess) -> Optional[HostAccess]:
        """Store one login. Returns None when it was already there."""
        try:
            model = HostAccessModel(
                occurred_at=entry.occurred_at,
                os_user=entry.os_user[:64],
                source_ip=entry.source_ip[:64],
                method=entry.method[:32],
                result=entry.result[:16],
            )
            self.session.add(model)
            self.session.commit()
            return self._toEntity(model)
        except IntegrityError:
            # Already recorded: the script re-sent an overlapping window.
            self.session.rollback()
            return None
        except Exception as e:
            self.session.rollback()
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def findRecent(self, params: Optional[PaginationParams] = None) -> list[HostAccess] | PaginatedResponse[HostAccess]:
        try:
            query = self.session.query(HostAccessModel).order_by(HostAccessModel.occurred_at.desc())

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
