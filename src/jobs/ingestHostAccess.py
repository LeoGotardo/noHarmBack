"""Record SSH logins to the machine, from the host's own journal.

Run from the host, not from the API process:

    journalctl -u ssh --since "-15 min" -o short-iso --no-pager \\
      | docker compose exec -T app ingest-host-access

## Why this is a job and not an endpoint

The collector runs on the host, as root, from cron — on the same machine as the
Docker socket. Giving it an HTTP endpoint would mean inventing a shared secret
to generate, store and rotate, plus a public write path into a security audit
table, plus a rate limit to size, plus constant-time comparison — all to
authenticate a process that already has more authority than the token would
grant. `docker exec` authenticates it by unix permissions on the socket, which
is the thing actually being trusted.

A source-address check was the alternative and does not work: a request from
the host reaches the container from the Docker bridge gateway (172.18.0.1), not
from 127.0.0.1, and widening the rule to the bridge authorises every container
on it.

The cost is that this only exists on the single-host deployment. So does
`auth.log`: on the ECS path in `infra/` there is no journal to read, and this
feature has no meaning there either way.

## No cursor file

The collector re-sends an overlapping window (15 minutes, every 10) and the
database deduplicates. The unique index on (instant, address, user) is what
makes that safe, and it means there is no cursor to lose, corrupt, or get out of
step with a clock change — the failure mode of a state file is silently
skipping the window where something happened.

## Accepted only

Failed attempts are parsed and counted but **not stored as rows**. A public SSH
port collects thousands of them a day, and they would bury the handful of
successful logins that are the entire point of the table. The count goes to the
run's log; brute force belongs with the suspicious-traffic counters, where it is
a number rather than a transcript.

## What this is not

Proof. Anyone with root can edit the journal before the collector reads it. It
catches access nobody expected and carelessness, not an attacker covering their
tracks, and reading it as if it did would be worse than not having it.

Exit codes: 0 on a clean run (including an empty window), 1 when the run failed.
"""

import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from core.database import database
from domain.entities.errorLog import HostAccess
from infrastructure.database.repositories.hostAccessRepository import HostAccessRepository
from websocket.emitter import notifyAdmins

logger = logging.getLogger("noharm.ingestHostAccess")


# `journalctl -o short-iso` prefixes each line with an ISO instant and the unit,
# then sshd's own message. Anchored on the message so a hostname containing the
# word "for" cannot shift the groups.
_LINE = re.compile(
    r"^(?P<when>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4})\s+"
    r"\S+\s+sshd\[\d+\]:\s+"
    r"(?P<result>Accepted|Failed)\s+(?P<method>\S+)\s+for\s+"
    r"(?:invalid user\s+)?(?P<user>\S+)\s+from\s+(?P<ip>\S+)\s+port\s+\d+"
)

# A single run should never write more than a handful. A window full of
# successful logins is either a misconfigured collector or something worth
# looking at by hand, and either way the answer is not to insert ten thousand
# rows unattended.
_MAX_PER_RUN = 500


class _SessionDb:
    """Minimal Database-shaped wrapper, matching what repositories expect.

    No RLS context: `tb_15`'s policy passes only for a session without one,
    which is what keeps this table out of every request path.
    """

    def __init__(self, session):
        self._session = session
        self.engine = database.engine

    @property
    def session(self):
        return self._session


def parseLine(line: str) -> Optional[HostAccess]:
    """One journal line into a login, or None when it is not one.

    The instant comes from the journal, never from the clock: a re-sent window
    has to produce the same natural key, and `datetime.now()` would make every
    re-send a new row.

    Stored as naive UTC, like every other instant in this schema. The journal
    prints local time with an offset, so a machine outside UTC would otherwise
    write timestamps the next comparison reads as hours off — the exact failure
    the suspension and deletion columns are documented to avoid.
    """
    match = _LINE.match(line.strip())
    if match is None:
        return None

    when = datetime.strptime(match.group("when"), "%Y-%m-%dT%H:%M:%S%z")

    return HostAccess(
        occurred_at=when.astimezone(timezone.utc).replace(tzinfo=None),
        os_user=match.group("user"),
        source_ip=match.group("ip"),
        method=match.group("method"),
        result=match.group("result").lower(),
    )


def ingest(lines) -> dict:
    """Read journal lines, store the successful logins, count the rest."""
    session = database.session
    repository = HostAccessRepository(_SessionDb(session))

    stored = duplicates = failures = unparsed = 0

    try:
        for line in lines:
            if not line.strip():
                continue

            entry = parseLine(line)
            if entry is None:
                unparsed += 1
                continue

            if entry.result != "accepted":
                failures += 1
                continue

            if stored >= _MAX_PER_RUN:
                logger.warning(
                    "stopped at %s logins in one run; the rest of the window was not read",
                    _MAX_PER_RUN,
                )
                break

            if repository.record(entry) is None:
                duplicates += 1
            else:
                stored += 1
                # Every one, not just the first: two logins from two addresses
                # is the thing worth knowing about, and there is no equivalent
                # of a crash loop here.
                notifyAdmins(
                    "host_access",
                    "SSH login to the server",
                    f"{entry.os_user} from {entry.source_ip}",
                    ip=entry.source_ip,
                )

        return {
            "stored": stored,
            "duplicates": duplicates,
            "failures": failures,
            "unparsed": unparsed,
        }
    finally:
        session.close()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [ingest-host-access] %(levelname)s %(message)s",
    )

    try:
        result = ingest(sys.stdin)
    except Exception:
        logger.exception("host access ingestion aborted")
        return 1

    logger.info(
        "%s new login(s), %s already recorded, %s failed attempt(s) not stored, %s line(s) ignored",
        result["stored"], result["duplicates"], result["failures"], result["unparsed"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
