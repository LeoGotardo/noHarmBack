"""Unit tests for the suspicious traffic counter.

Two things are worth pinning down. `classify` decides what gets written at all,
so a mistake there is either a counter that misses the thing it exists for or a
write on every request — and the second is the reason this only counts
failures. And nothing in the class may raise: it runs inside a middleware, on
the way out, where an exception would change what the caller receives.
"""

import pytest
from unittest.mock import MagicMock

from core.config import config
from security.suspiciousTraffic import (
    NOT_FOUND,
    OTHER_CLIENT,
    SERVER_ERROR,
    UNAUTHORISED,
    SuspiciousTraffic,
    classify,
)


class TestClassify:
    @pytest.mark.parametrize("status", [200, 201, 204, 301, 302, 304])
    def test_success_and_redirects_are_not_counted(self, status):
        """The reason this is affordable: a counter on every request is a write
        on every request, and nobody scans for /.env and gets a 200."""
        assert classify(status, "/anything") is None

    def test_a_404_is_path_scanning(self):
        assert classify(404, "/.env") == NOT_FOUND

    @pytest.mark.parametrize("status", [401, 403])
    def test_401_and_403_are_credential_probing(self, status):
        """Separate from 404 on purpose: mapping the surface and trying keys
        are different intentions, and one counter would mean neither."""
        assert classify(status, "/users/me") == UNAUTHORISED

    def test_429_is_not_counted_twice(self):
        """It is already the rate limiter's own answer; counting it here would
        report the same event under a second name."""
        assert classify(429, "/auth/login") is None

    @pytest.mark.parametrize("status", [500, 502, 503])
    def test_server_errors_have_their_own_counter(self, status):
        assert classify(status, "/streaks/start") == SERVER_ERROR

    @pytest.mark.parametrize("status", [400, 409, 422])
    def test_other_client_errors_share_a_counter(self, status):
        assert classify(status, "/reports/x") == OTHER_CLIENT


class TestRecord:
    def _tracker(self):
        client = MagicMock()
        return SuspiciousTraffic(client), client

    def test_it_increments_and_refreshes_the_window(self, monkeypatch):
        """The expiry is refreshed on every hit, so the window is 'since they
        stopped' rather than 'since they started': a burst that keeps going
        keeps its count, one that stops ages out."""
        tracker, client = self._tracker()

        tracker.record("203.0.113.4", NOT_FOUND)

        pipe = client.pipeline.return_value
        pipe.incr.assert_called_once_with("nh:sus:notfound:203.0.113.4")
        pipe.expire.assert_called_once_with(
            "nh:sus:notfound:203.0.113.4", config.SUSPICIOUS_WINDOW_SECONDS
        )
        pipe.execute.assert_called_once()

    def test_a_redis_failure_never_escapes(self):
        """It runs in a middleware on the way out; raising would change what
        the caller receives because a metric could not be written."""
        tracker, client = self._tracker()
        client.pipeline.side_effect = RuntimeError("redis is gone")

        tracker.record("203.0.113.4", NOT_FOUND)

    def test_no_client_is_a_no_op(self):
        tracker = SuspiciousTraffic(None)
        tracker._redis = None

        tracker.record("203.0.113.4", NOT_FOUND)
        assert tracker.flagged() == []

    @pytest.mark.parametrize("ip,kind", [("", NOT_FOUND), ("1.2.3.4", ""), ("", "")])
    def test_a_missing_address_or_kind_writes_nothing(self, ip, kind):
        tracker, client = self._tracker()

        tracker.record(ip, kind)

        client.pipeline.assert_not_called()


class TestFlagged:
    def _tracker(self, keys: dict[str, int]):
        client = MagicMock()
        client.scan_iter.return_value = iter(keys)
        client.get.side_effect = lambda key: str(keys[key])
        return SuspiciousTraffic(client)

    def test_an_address_past_a_threshold_is_flagged_with_its_reason(self):
        tracker = self._tracker(
            {f"nh:sus:notfound:1.2.3.4": config.SUSPICIOUS_NOT_FOUND_THRESHOLD + 5}
        )

        flagged = tracker.flagged()

        assert len(flagged) == 1
        assert flagged[0]["ip"] == "1.2.3.4"
        assert flagged[0]["reasons"] == [NOT_FOUND]

    def test_counts_below_the_threshold_are_reported_but_are_not_reasons(self):
        """The number is still useful context beside a kind that did trip."""
        tracker = self._tracker(
            {
                "nh:sus:notfound:1.2.3.4": config.SUSPICIOUS_NOT_FOUND_THRESHOLD + 1,
                "nh:sus:client:1.2.3.4": 1,
            }
        )

        entry = tracker.flagged()[0]

        assert entry["counts"]["client"] == 1
        assert entry["reasons"] == [NOT_FOUND]

    def test_an_address_below_every_threshold_is_not_flagged(self):
        tracker = self._tracker({"nh:sus:notfound:1.2.3.4": 1})

        assert tracker.flagged() == []

    def test_the_worst_address_comes_first(self):
        tracker = self._tracker(
            {
                "nh:sus:notfound:1.1.1.1": config.SUSPICIOUS_NOT_FOUND_THRESHOLD + 1,
                "nh:sus:notfound:2.2.2.2": config.SUSPICIOUS_NOT_FOUND_THRESHOLD + 900,
            }
        )

        assert [entry["ip"] for entry in tracker.flagged()] == ["2.2.2.2", "1.1.1.1"]

    def test_a_read_failure_answers_empty_rather_than_raising(self):
        client = MagicMock()
        client.scan_iter.side_effect = RuntimeError("redis is gone")

        assert SuspiciousTraffic(client).flagged() == []
