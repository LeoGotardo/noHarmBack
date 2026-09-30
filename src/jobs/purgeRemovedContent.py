"""Delete posts and comments a moderator removed long enough ago.

Run as a one-shot task, not from the API process:

    docker compose run --rm app purge-removed-content

`docker/entrypoint.sh` maps that argument here, and the live instance runs it
from cron beside the other two purges (see `docs/operations.md`).

A moderator's removal is a status, not a delete, so an appeal can put the post
back. That makes it data the system still holds about the author, and the
Privacy Policy promises how long: `REMOVED_CONTENT_RETENTION_DAYS` (default 30)
from the removal. This is what keeps that promise. A post's comments and likes
go with it through the foreign keys.

What the author deletes themselves never reaches this job — that is a real
DELETE at the time. If the removed item was reported, the copy in the report's
evidence (`tb_11`) is untouched here and follows `REPORT_EVIDENCE_RETENTION_DAYS`
instead.

Exit codes: 0 on a clean run (including when there was nothing to delete), 1
when the sweep failed.
"""

import logging
import sys

from datetime import datetime, timedelta, timezone

from core.config import config
from core.database import database
from infrastructure.database.repositories.postCommentRepository import PostCommentRepository
from infrastructure.database.repositories.postRepository import PostRepository

logger = logging.getLogger("noharm.purgeRemovedContent")


class _SessionDb:
    """Minimal Database-shaped wrapper, matching what repositories expect.

    Without an RLS context on purpose: the delete policies on tb_16 and tb_17
    let only an author or a context-free session through, and this job is
    neither author.
    """

    def __init__(self, session):
        self._session = session
        self.engine = database.engine

    @property
    def session(self):
        return self._session


def purgeRemovedContent() -> tuple[int, int]:
    """Delete removed items past the window. Returns (posts, comments) removed."""
    retentionDays = config.REMOVED_CONTENT_RETENTION_DAYS
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=retentionDays)
    session = database.session

    try:
        db = _SessionDb(session)
        # Comments first: a removed comment under a removed post would go with
        # the post anyway, and counting it here keeps the log honest about
        # what this run removed on its own account.
        comments = PostCommentRepository(db).deleteRemovedBefore(cutoff)
        posts = PostRepository(db).deleteRemovedBefore(cutoff)

        if posts or comments:
            logger.info(
                "deleted %s post(s) and %s comment(s) removed over %s days ago",
                posts, comments, retentionDays
            )
        else:
            logger.info("nothing removed over %s days ago", retentionDays)

        return posts, comments
    finally:
        session.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [purge-removed-content] %(levelname)s %(message)s",
    )

    try:
        purgeRemovedContent()
    except Exception:
        logger.exception("removed content purge run aborted")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
