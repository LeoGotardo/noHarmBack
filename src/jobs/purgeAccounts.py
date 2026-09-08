"""Permanently delete accounts whose deletion grace window has closed.

Run as a one-shot task, not from the API process:

    docker compose run --rm app purge-accounts

`docker/entrypoint.sh` maps that argument here, and the live instance runs it
from cron (see `docs/operations.md`). Nothing in the request path purges
anything — deletion is a soft delete plus a clock, and this is the only thing
that stops the clock.

What "purged" means: the `tb_0` row is deleted, and the ON DELETE actions from
migration `20260901_01` take the rest with it — streaks, friendships, chats and
their messages, user_badges, refresh tokens, device tokens. Audit log rows
survive with a null `catalyst_id`, so the record that an account existed and was
deleted outlives the account itself while pointing at nobody.

Exit codes: 0 when every eligible account was purged (including when there were
none), 1 when at least one failed. A failure on one account does not stop the
others — a single poisoned row must not keep the queue from draining night after
night.
"""

import logging
import sys

from core.config import config
from core.database import database
from infrastructure.database.repositories.userRepository import UserRepository

logger = logging.getLogger("noharm.purge")


class _SessionDb:
    """Minimal Database-shaped wrapper, matching what repositories expect.

    Deliberately without an RLS context. The `tb_0` UPDATE/DELETE policies read
    `app_current_user_id() IS NULL OR cl_0a = app_current_user_id()`, so an
    unset context passes — which is what lets a job that belongs to no user
    delete rows belonging to many. Setting a context here would restrict the
    purge to a single account and silently delete nothing.
    """

    def __init__(self, session):
        self._session = session
        self.engine = database.engine

    @property
    def session(self):
        return self._session


def purgeExpiredAccounts() -> int:
    """Purge every account past its grace window. Returns the failure count."""
    graceDays = config.ACCOUNT_DELETION_GRACE_DAYS
    session = database.session

    try:
        repository = UserRepository(_SessionDb(session))
        userIds = repository.findExpiredDeleted(graceDays)

        if not userIds:
            logger.info("no accounts past the %s-day deletion window", graceDays)
            return 0

        logger.info("purging %s account(s) past the %s-day deletion window", len(userIds), graceDays)

        failures = 0
        for userId in userIds:
            try:
                repository.purge(userId)
                # The id is written to the log on purpose: it is the last trace
                # of the account outside the audit table, and a restore request
                # arriving after a purge has to be answerable with something
                # more useful than silence.
                logger.info("purged account %s", userId)
            except Exception:
                failures += 1
                logger.exception("failed to purge account %s", userId)

        return failures
    finally:
        session.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [purge-accounts] %(levelname)s %(message)s",
    )

    try:
        failures = purgeExpiredAccounts()
    except Exception:
        logger.exception("purge run aborted")
        return 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
