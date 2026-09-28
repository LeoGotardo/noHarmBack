"""Drop faults nothing has hit in a long time.

Run as a one-shot task, not from the API process:

    docker compose run --rm app purge-errors

`docker/entrypoint.sh` maps that argument here, and the live instance runs it
from cron beside the other two sweeps (see `docs/operations.md`).

`tb_14` is grouped by fingerprint, so its row count is the number of *distinct*
faults rather than occurrences — it grows slowly and a crash loop does not grow
it at all. It still needs a window, for two reasons that have nothing to do with
disk:

- the traceback column is encrypted because it carries message bodies and
  e-mail addresses, and data kept without a reason to keep it is the thing every
  other retention rule in this system exists to prevent;
- a fault nobody has seen in three months is not a fault anyone is debugging,
  and a panel showing it is a panel with older noise than signal.

`ERROR_LOG_RETENTION_DAYS` (default 90) is measured from `last_seen`, not from
when the row was created: a bug first seen in January and still firing today is
current, and deleting it on its birthday would be exactly wrong.

Exit codes: 0 on a clean run (including when there was nothing to delete), 1
when the sweep failed.
"""

import logging
import sys

from core.config import config
from core.database import database
from infrastructure.database.repositories.errorLogRepository import ErrorLogRepository

logger = logging.getLogger("noharm.purgeErrors")


class _SessionDb:
    """Minimal Database-shaped wrapper, matching what repositories expect.

    Without an RLS context on purpose: `tb_14`'s policy passes only when
    `app.current_user_id` is unset, which is what keeps this table out of every
    request path.
    """

    def __init__(self, session):
        self._session = session
        self.engine = database.engine

    @property
    def session(self):
        return self._session


def purgeStaleErrors() -> int:
    """Delete faults past the retention window. Returns the number removed."""
    retentionDays = config.ERROR_LOG_RETENTION_DAYS
    session = database.session

    try:
        repository = ErrorLogRepository(_SessionDb(session))
        deleted = repository.purgeOlderThan(retentionDays)

        if deleted:
            logger.info(
                "deleted %s fault(s) last seen over %s days ago", deleted, retentionDays
            )
        else:
            logger.info("no fault older than the %s-day window", retentionDays)

        return deleted
    finally:
        session.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [purge-errors] %(levelname)s %(message)s",
    )

    try:
        purgeStaleErrors()
    except Exception:
        logger.exception("error purge run aborted")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
