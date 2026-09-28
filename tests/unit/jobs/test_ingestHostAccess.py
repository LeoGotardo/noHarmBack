"""Unit tests for the SSH access ingestion.

The parser is the part that fails quietly: a regex that stops matching turns
into an empty window, which looks exactly like "nobody logged in" — the one
answer this table must never give by accident.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from jobs.ingestHostAccess import ingest, parseLine


# Real shapes, as `journalctl -u ssh -o short-iso` prints them.
ACCEPTED = (
    "2026-09-18T14:22:01+0000 ip-10-0-0-4 sshd[4711]: "
    "Accepted publickey for ubuntu from 203.0.113.4 port 54321 ssh2: "
    "RSA SHA256:abcdef"
)
FAILED = (
    "2026-09-18T14:23:10+0000 ip-10-0-0-4 sshd[4712]: "
    "Failed password for invalid user admin from 198.51.100.7 port 4444 ssh2"
)


class TestParse:
    def test_an_accepted_login(self):
        entry = parseLine(ACCEPTED)

        assert entry.os_user == "ubuntu"
        assert entry.source_ip == "203.0.113.4"
        assert entry.method == "publickey"
        assert entry.result == "accepted"

    def test_the_instant_comes_from_the_journal_not_the_clock(self):
        """A re-sent window has to produce the same natural key. `now()` would
        make every re-send a new row and defeat the deduplication."""
        assert parseLine(ACCEPTED).occurred_at == datetime(2026, 9, 18, 14, 22, 1)

    def test_a_non_utc_offset_is_converted_not_truncated(self):
        """The journal prints local time with an offset; the schema stores naive
        UTC. Dropping the offset instead of applying it writes a timestamp the
        next comparison reads as hours off."""
        line = ACCEPTED.replace("+0000", "-0300")

        # 14:22 at UTC-3 is 17:22 UTC.
        assert parseLine(line).occurred_at == datetime(2026, 9, 18, 17, 22, 1)

    def test_a_failed_attempt_parses_and_is_labelled(self):
        entry = parseLine(FAILED)

        assert entry.result == "failed"
        # "invalid user admin" must yield the account, not the words before it.
        assert entry.os_user == "admin"
        assert entry.source_ip == "198.51.100.7"

    @pytest.mark.parametrize(
        "line",
        [
            "",
            "not a journal line at all",
            "2026-09-18T14:22:01+0000 host sshd[1]: Connection closed by 1.2.3.4",
            "2026-09-18T14:22:01+0000 host cron[1]: Accepted publickey for ubuntu from 1.2.3.4 port 1 ssh2",
        ],
    )
    def test_lines_that_are_not_logins_are_ignored(self, line):
        """Including one from another unit that happens to contain the words —
        the pattern is anchored on sshd for exactly that reason."""
        assert parseLine(line) is None

    def test_a_hostname_containing_for_does_not_shift_the_groups(self):
        line = ACCEPTED.replace("ip-10-0-0-4", "server-for-prod")

        entry = parseLine(line)
        assert entry.os_user == "ubuntu"
        assert entry.source_ip == "203.0.113.4"


class TestIngest:
    def _run(self, lines, record=None):
        with patch("jobs.ingestHostAccess.database"), patch(
            "jobs.ingestHostAccess.HostAccessRepository"
        ) as Repo:
            Repo.return_value.record.side_effect = record or (lambda entry: entry)
            return ingest(lines), Repo.return_value

    def test_only_successful_logins_are_stored(self):
        """A public SSH port collects thousands of failures a day; storing them
        would bury the few logins the table exists for."""
        result, repo = self._run([ACCEPTED, FAILED, FAILED])

        assert result["stored"] == 1
        assert result["failures"] == 2
        assert repo.record.call_count == 1

    def test_a_duplicate_is_counted_not_an_error(self):
        """The collector re-sends an overlapping window on purpose."""
        result, _ = self._run([ACCEPTED], record=lambda entry: None)

        assert result["stored"] == 0
        assert result["duplicates"] == 1

    def test_unreadable_lines_are_counted_rather_than_dropped_silently(self):
        result, _ = self._run([ACCEPTED, "garbage", ""])

        assert result["stored"] == 1
        assert result["unparsed"] == 1

    def test_a_run_is_capped(self):
        """A window full of logins is a broken collector or something worth
        looking at by hand — either way, not ten thousand unattended inserts."""
        result, repo = self._run([ACCEPTED.replace(":01+", f":{i:02d}+") for i in range(10, 60)] * 20)

        assert result["stored"] <= 500
        assert repo.record.call_count <= 500
