"""Drop the evidence behind reports a moderator closed long enough ago.

Run as a one-shot task, not from the API process:

    docker compose run --rm app purge-evidence

`docker/entrypoint.sh` maps that argument here, and the live instance runs it
from cron beside the account purge (see `docs/operations.md`).

What goes and what stays: the **evidence** rows in `tb_11` — copied private
messages and a profile snapshot — are deleted once the report they belong to has
been resolved for `REPORT_EVIDENCE_RETENTION_DAYS` (default 180). The **report**
survives forever: reason, status, the account it named. That split is the whole
point. A moderator has to be able to answer "what was decided about this
account, and when"; nobody needs to keep reading two strangers' conversation a
year after deciding it.

An open report is never swept, however old it is. Evidence removed before anyone
read it would leave a queue of complaints that can no longer be judged — if that
ever starts happening, the answer is a moderator, not a shorter window.

Exit codes: 0 on a clean run (including when there was nothing to delete), 1
when the sweep failed.
"""

import logging
import sys

from core.config import config
from core.database import database
from infrastructure.database.repositories.reportEvidenceRepository import ReportEvidenceRepository

logger = logging.getLogger("noharm.purgeEvidence")


class _SessionDb:
    """Minimal Database-shaped wrapper, matching what repositories expect.

    Deliberately without an RLS context: `tb_11`'s delete policy passes only
    when `app_current_user_id()` is unset, which is what keeps deletion out of
    every request path and inside this job.
    """

    def __init__(self, session):
        self._session = session
        self.engine = database.engine

    @property
    def session(self):
        return self._session


def purgeExpiredEvidence() -> int:
    """Delete evidence past the retention window. Returns the number removed."""
    retentionDays = config.REPORT_EVIDENCE_RETENTION_DAYS
    session = database.session

    try:
        repository = ReportEvidenceRepository(_SessionDb(session))
        deleted = repository.deleteExpired(retentionDays)

        if deleted:
            logger.info(
                "deleted %s evidence item(s) from reports resolved over %s days ago",
                deleted, retentionDays
            )
        else:
            logger.info("no evidence past the %s-day retention window", retentionDays)

        return deleted
    finally:
        session.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [purge-evidence] %(levelname)s %(message)s",
    )

    try:
        purgeExpiredEvidence()
    except Exception:
        logger.exception("evidence purge run aborted")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
