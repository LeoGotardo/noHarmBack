from domain.entities.report import Report
from core.errorUtils import excLocation
from infrastructure.database.models.reportModel import ReportModel
from exceptions.baseExceptions import NoHarmException
from schemas.paginationSchemas import PaginationParams, PaginatedResponse, createPaginatedResponse

from core.database import Database
from core.config import config

from sqlalchemy import case, func

from datetime import datetime, timezone
from typing import Optional


class ReportRepository:
    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine


    def _toEntity(self, model: ReportModel) -> Report:
        return Report(
            id=model.id,
            reporter=model.reporter,
            reported=model.reported,
            reported_uid=model.reported_uid,
            reported_username=model.reported_username,
            reason=model.reason,
            details=model.details,
            status=model.status,
            locked_by=model.locked_by,
            locked_at=model.locked_at,
            created_at=model.created_at,
            updated_at=model.updated_at
        )


    def _paginate(self, query, params: Optional[PaginationParams]):
        if params:
            total = query.count()
            offset = (params.page - 1) * params.pageSize
            items = [self._toEntity(item) for item in query.offset(offset).limit(params.pageSize).all()]

            return createPaginatedResponse(items, total, params.page, params.pageSize)

        return [self._toEntity(item) for item in query.all()]


    def findById(self, id: str, returnModel: bool = False) -> Report | ReportModel:
        """Find a report by ID

        Args:
            id (str): Report ID

        Returns:
            Report: Report with his full data
        """
        try:
            reportModel = self.session.query(ReportModel).filter(ReportModel.id == id).first()
            if reportModel:
                return reportModel if returnModel else self._toEntity(reportModel)
            raise NoHarmException(statusCode=404, message="Report not found")
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findRecentByPair(self, reporterId: str, reportedId: str) -> Optional[Report]:
        """The reporter's most recent report about this user, whatever became of it.

        Returns None rather than raising: "never reported them" is the ordinary
        case on the way to creating one.

        Deliberately not filtered by status. The open one is a duplicate, but a
        *dismissed* one is the more interesting answer: without it, "ignored" is
        a round trip rather than a decision, and the same complaint comes back
        the minute a moderator closes it. The service decides what each outcome
        means; the repository just hands back the latest.

        Matched on `reported_uid`, not on the foreign key: an account purged
        while a report about it was open leaves the key NULL, and matching on
        that would make every such report collapse into one another's duplicate.
        """
        try:
            reportModel = self.session.query(ReportModel).filter(
                ReportModel.reporter == reporterId,
                ReportModel.reported_uid == reportedId
            ).order_by(ReportModel.created_at.desc()).first()

            return self._toEntity(reportModel) if reportModel else None
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findByReporter(self, reporterId: str, params: Optional[PaginationParams] = None) -> list[Report] | PaginatedResponse[Report]:
        """Find every report filed by a user, newest first, optionally paginated."""
        try:
            query = self.session.query(ReportModel).filter(
                ReportModel.reporter == reporterId
            ).order_by(ReportModel.created_at.desc())

            return self._paginate(query, params)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def _reporterStandingSubquery(self):
        """Per-reporter tallies of how their past reports were decided.

        One grouped pass over `tb_10`, joined back to it, rather than a
        correlated count per row. Kept private because it is an ordering
        detail: callers ask for a sort, not for a join.
        """
        return (
            self.session.query(
                ReportModel.reporter.label("reporter"),
                func.sum(
                    case((ReportModel.status == config.STATUS_CODES["accepted"], 1), else_=0)
                ).label("accepted"),
                func.sum(
                    case((ReportModel.status == config.STATUS_CODES["ignored"], 1), else_=0)
                ).label("ignored"),
            )
            .group_by(ReportModel.reporter)
            .subquery()
        )


    def findAll(
        self,
        status: Optional[int] = None,
        params: Optional[PaginationParams] = None,
        sort: str = "newest"
    ) -> list[Report] | PaginatedResponse[Report]:
        """Every report — the moderation queue.

        Reached only through the admin route, which uses a session with no RLS
        context on purpose: the select policy is reporter-only.

        `sort`:

        - `newest` (default) — chronological, as it always was.
        - `priority` — self-harm reports first, then by how the reporter's past
          reports were decided, then newest. Nothing is hidden or dropped: a
          report from someone whose complaints are always dismissed still sits
          in the queue, just not ahead of everyone else's.

        **Self-harm is ordered first regardless of who filed it.** In a recovery
        app that report is usually a frightened friend, and the cost of reading
        a baseless one late is not symmetric with the cost of reading a real one
        late. A reporter's history is a reason to read them later, never a
        reason to read that one later.
        """
        try:
            query = self.session.query(ReportModel)
            if status is not None:
                query = query.filter(ReportModel.status == status)

            if sort == "priority":
                standings = self._reporterStandingSubquery()
                query = query.outerjoin(standings, ReportModel.reporter == standings.c.reporter)

                accepted = func.coalesce(standings.c.accepted, 0)
                ignored = func.coalesce(standings.c.ignored, 0)

                # Laplace-smoothed acceptance rate, the same figure the queue
                # shows beside each row. The +1/+2 is what keeps a brand-new
                # reporter at 0.5 instead of at zero: nobody starts out
                # distrusted for having no history.
                weight = (accepted + 1.0) / (accepted + ignored + 2.0)

                query = query.order_by(
                    case((ReportModel.reason == "self_harm", 0), else_=1),
                    weight.desc(),
                    ReportModel.created_at.desc()
                )
            else:
                query = query.order_by(ReportModel.created_at.desc())

            return self._paginate(query, params)
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def countByReported(self, reportedId: str, status: Optional[int] = None) -> int:
        """How many reports name this user — the number moderation ranks on.

        Counts on the snapshot, so the answer does not drop to zero the day the
        account is purged.
        """
        try:
            query = self.session.query(ReportModel).filter(ReportModel.reported_uid == reportedId)
            if status is not None:
                query = query.filter(ReportModel.status == status)

            return query.count()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def countByReporter(self, reporterId: str, status: Optional[int] = None) -> int:
        """How many reports this user has filed — the backlog check reads this.

        The mirror of `countByReported`: that one asks how much trouble an
        account is in, this one asks how much of the queue one account is
        responsible for.
        """
        try:
            query = self.session.query(ReportModel).filter(ReportModel.reporter == reporterId)
            if status is not None:
                query = query.filter(ReportModel.status == status)

            return query.count()
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def standingsByReporters(self, reporterIds: list[str]) -> dict[str, dict[str, int]]:
        """How each of these reporters' past reports were decided.

        One grouped query for the whole page, not one per row: the moderation
        queue shows this beside every report, and the per-row version is an
        N+1 that grows with the page size.

        Returns `{reporterId: {"pending": n, "accepted": n, "ignored": n}}`,
        with every requested id present so callers never have to guess whether
        a missing key means zero or means the query skipped it.
        """
        base = {key: 0 for key in ("pending", "accepted", "ignored")}
        standings: dict[str, dict[str, int]] = {rid: dict(base) for rid in reporterIds if rid}

        if not standings:
            return {}

        try:
            rows = (
                self.session.query(
                    ReportModel.reporter,
                    ReportModel.status,
                    func.count().label("total")
                )
                .filter(ReportModel.reporter.in_(list(standings.keys())))
                .group_by(ReportModel.reporter, ReportModel.status)
                .all()
            )
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

        byCode = {config.STATUS_CODES[name]: name for name in base}

        for reporterId, status, total in rows:
            name = byCode.get(status)
            if name is not None and reporterId in standings:
                standings[reporterId][name] = int(total)

        return standings


    def countOpenAgainstMany(self, reportedIds: list[str]) -> dict[str, int]:
        """Open reports against each of these users, in one query.

        Feeds the queue's "several people reported this account" signal. Grouped
        for the same reason as `standingsByReporters`: it is read once per row
        of a page.
        """
        wanted = [rid for rid in reportedIds if rid]
        if not wanted:
            return {}

        try:
            rows = (
                self.session.query(ReportModel.reported_uid, func.count().label("total"))
                .filter(
                    ReportModel.reported_uid.in_(wanted),
                    ReportModel.status == config.STATUS_CODES["pending"]
                )
                .group_by(ReportModel.reported_uid)
                .all()
            )
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

        counts = {rid: 0 for rid in wanted}
        for reportedId, total in rows:
            counts[reportedId] = int(total)

        return counts


    def create(self, report: Report) -> Report:
        """Create a report

        Args:
            report (Report): Report to create

        Returns:
            Report: Report with his full data
        """
        try:
            reportModel = ReportModel(
                reporter=report.reporter,
                reported=report.reported,
                reported_uid=report.reported_uid or report.reported,
                reported_username=report.reported_username,
                reason=report.reason,
                details=report.details,
                status=report.status
            )

            self.session.add(reportModel)
            self.session.commit()

            return self._toEntity(reportModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def claim(self, id: str, moderatorId: str) -> Report:
        """Mark a report as being reviewed by `moderatorId`.

        Unconditional: the caller decides whether the lock is free, because
        "free" means "unheld, held by me, or held by someone who walked away
        `REPORT_LOCK_MINUTES` ago" — a rule about the clock, not about the row.
        """
        try:
            reportModel = self.findById(id, returnModel=True)

            reportModel.locked_by = moderatorId
            reportModel.locked_at = datetime.now(timezone.utc).replace(tzinfo=None)

            self.session.commit()

            return self._toEntity(reportModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def releaseLock(self, id: str) -> Report:
        """Drop the review lock, leaving the report where it was."""
        try:
            reportModel = self.findById(id, returnModel=True)

            reportModel.locked_by = None
            reportModel.locked_at = None

            self.session.commit()

            return self._toEntity(reportModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def updateStatus(self, id: str, status: str) -> Report:
        """Update a report status

        Args:
            id (str): Report ID
            status (str): New status key ("accepted" = actioned, "ignored" = dismissed)

        Returns:
            Report: Report with his full data
        """
        try:
            reportModel = self.findById(id, returnModel=True)

            reportModel.status = config.STATUS_CODES[status]
            # A resolved report is nobody's to review any more. Leaving the lock
            # behind would make the queue's "in review" column lie for half an
            # hour after the decision.
            reportModel.locked_by = None
            reportModel.locked_at = None

            self.session.commit()

            return self._toEntity(reportModel)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
