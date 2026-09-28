"""Unit tests for ErrorLogService.

Two things decide whether this class is worth having: the fingerprint groups
the right failures together, and nothing it does can ever become the failure.
"""

import pytest
from unittest.mock import MagicMock

from domain.services.errorLogService import ErrorLogService


def _raise(exc):
    """Give an exception a real traceback — `extract_tb` has nothing without one."""
    try:
        raise exc
    except type(exc) as caught:
        return caught


def _make_service(mock_db):
    service = ErrorLogService(mock_db)
    service.repository = MagicMock()
    return service


# ── the fingerprint ───────────────────────────────────────────────────────────

def test_the_same_fault_twice_is_one_fingerprint(mock_db):
    """Same raise site, same call site, same route — one row.

    Both hits go through the identical line here on purpose. Two `try` blocks
    on different lines would be two different call sites, and the fingerprint
    is *meant* to tell those apart: the same helper failing when called from
    two places is usually two bugs.
    """
    service = _make_service(mock_db)

    def boom():
        raise ValueError("user 3f2a not found")

    prints = []
    for _ in range(2):
        try:
            boom()
        except ValueError as e:
            prints.append(service.fingerprint(e, "/users/me"))

    assert prints[0] == prints[1]


def test_two_call_sites_of_the_same_helper_are_two_faults(mock_db):
    """The other half of the rule, and the reason the test above loops."""
    service = _make_service(mock_db)

    def boom():
        raise ValueError("same message")

    try:
        boom()
    except ValueError as e:
        first = service.fingerprint(e, "/users/me")
    try:
        boom()
    except ValueError as e:
        second = service.fingerprint(e, "/users/me")

    assert first != second


def test_the_message_does_not_change_the_fingerprint(mock_db):
    """"User 3f2a not found" and "user 91bc not found" are one bug, and keying
    on the text would file them as two — and put a user id in a column meant to
    be safe to read."""
    service = _make_service(mock_db)

    def boom(uid):
        raise ValueError(f"user {uid} not found")

    prints = []
    for uid in ("3f2a", "91bc"):
        try:
            boom(uid)
        except ValueError as e:
            prints.append(service.fingerprint(e, "/users/me"))

    assert prints[0] == prints[1]


def test_a_different_route_is_a_different_fault(mock_db):
    service = _make_service(mock_db)
    exc = _raise(ValueError("x"))

    assert service.fingerprint(exc, "/users/me") != service.fingerprint(exc, "/streaks/start")


def test_a_different_exception_type_is_a_different_fault(mock_db):
    service = _make_service(mock_db)

    assert service.fingerprint(_raise(ValueError("x")), "/p") != service.fingerprint(
        _raise(KeyError("x")), "/p"
    )


# ── capture ───────────────────────────────────────────────────────────────────

def test_capture_records_the_type_status_and_route(mock_db):
    service = _make_service(mock_db)

    service.capture(
        _raise(ValueError("boom")),
        kind="unhandled",
        method="POST",
        path="/streaks/start",
        statusCode=500,
        userId="uid-001",
    )

    entry = service.repository.record.call_args.args[0]
    assert entry.exception_type == "ValueError"
    assert entry.status_code == 500
    assert entry.path == "/streaks/start"
    assert entry.method == "POST"
    assert entry.kind == "unhandled"
    assert entry.user_id == "uid-001"
    assert entry.fingerprint


def test_capture_keeps_the_traceback_and_the_message(mock_db):
    service = _make_service(mock_db)

    service.capture(
        _raise(ValueError("the detail")),
        kind="domain", method="GET", path="/p", statusCode=500,
    )

    entry = service.repository.record.call_args.args[0]
    assert entry.message == "the detail"
    assert "ValueError" in entry.traceback


def test_a_repository_failure_never_escapes(mock_db):
    """It runs inside an exception handler: raising here would replace the error
    the client is about to be told about with a different one."""
    service = _make_service(mock_db)
    service.repository.record.side_effect = RuntimeError("database is gone")

    service.capture(_raise(ValueError("boom")), kind="unhandled", method="GET", path="/p", statusCode=500)


def test_an_exception_with_no_traceback_still_records(mock_db):
    """`capture` is also reachable from a handler that was handed a bare
    exception, and `extract_tb(None)` is empty rather than an error."""
    service = _make_service(mock_db)

    service.capture(ValueError("never raised"), kind="http", method="GET", path="/p", statusCode=500)

    assert service.repository.record.called
