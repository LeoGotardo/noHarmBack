from infrastructure.database.repositories.errorLogRepository import ErrorLogRepository
from domain.entities.errorLog import ErrorLog
from core.database import Database
from websocket.emitter import notifyAdmins

from datetime import datetime, timezone
from typing import Optional
import hashlib
import logging
import traceback as tb


logger = logging.getLogger("noharm")

# How much of the traceback identifies the fault. The last frames are where it
# broke; everything above is how the request got there, which differs between
# two hits of the same bug (a different route, a different middleware order)
# and would split one fault into many rows.
_FINGERPRINT_FRAMES = 3

# A traceback is stored to be read, not scrolled. Anything past this is almost
# always the same framework stack repeated.
_MAX_TRACEBACK = 8000


def _utcNow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ErrorLogService:
    """Keeps a record of what is failing, without becoming a failure itself.

    Every method here is **fail-open**: it is called from the exception
    handlers in `main.py`, where raising would replace the error the user is
    about to be told about with a different one, and turn a 404 into a 500. A
    logger line is the fallback, because stdout is where all of this went
    before this table existed.
    """

    def __init__(self, db: Database):
        self.database: Database = db
        self.repository = ErrorLogRepository(self.database)

    @staticmethod
    def fingerprint(exc: BaseException, path: str) -> str:
        """What makes two failures the same failure.

        The exception type, the route, and the bottom few frames by file and
        line. Deliberately not the message: "User 3f2a not found" and "User
        91bc not found" are one bug, and keying on the text would file them as
        two — and would put a user id in a column that is meant to be safe to
        read.
        """
        frames = tb.extract_tb(exc.__traceback__)[-_FINGERPRINT_FRAMES:]
        where = "|".join(f"{f.filename}:{f.lineno}" for f in frames)
        seed = f"{type(exc).__name__}|{path}|{where}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def capture(
        self,
        exc: BaseException,
        *,
        kind: str,
        method: str,
        path: str,
        statusCode: int,
        userId: Optional[str] = None,
    ) -> None:
        """Record one occurrence. Never raises, never blocks the response."""
        try:
            entry = ErrorLog(
                kind=kind,
                path=path,
                method=method,
                fingerprint=self.fingerprint(exc, path),
                exception_type=type(exc).__name__,
                status_code=statusCode,
                last_seen=_utcNow(),
                message=str(exc) or None,
                traceback="".join(
                    tb.format_exception(type(exc), exc, exc.__traceback__)
                )[-_MAX_TRACEBACK:],
                user_id=userId,
            )
            recorded = self.repository.record(entry)

            # Only the first sighting. A crash loop is one fault that happened
            # four thousand times, and four thousand notifications is how an
            # alert channel gets muted — which costs the next real one.
            if recorded is not None and recorded.count == 1:
                notifyAdmins(
                    "error",
                    "New error in NoHarm",
                    f"{entry.exception_type} on {entry.method} {entry.path}",
                    fingerprint=entry.fingerprint,
                )
        except Exception:
            # The whole point of this class is that it cannot be the reason a
            # request fails. stdout is where every one of these went before the
            # table existed, so it is the right floor to fall back to.
            logger.warning("error log capture failed", exc_info=True)
