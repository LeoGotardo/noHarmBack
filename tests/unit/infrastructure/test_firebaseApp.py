"""The process-wide Firebase app, and the cold start that used to refuse logins.

`getFirebaseApp` memoises one app for the process. The interesting case is the
first moments after a restart, when several requests reach it at once: a second
caller must wait for the first to finish, not read a half-set flag and conclude
that authentication is unavailable.
"""

import importlib
import sys
import threading
import time
import types

import pytest


@pytest.fixture
def firebaseApp(monkeypatch):
    """A freshly imported module, so the memoised globals start empty."""
    import infrastructure.external.firebaseApp as module

    module = importlib.reload(module)
    monkeypatch.setattr(module, "isEmulated", lambda: True)
    return module


def _fakeFirebaseAdmin(monkeypatch, firebaseApp, delay=0.0, calls=None):
    """Stand in for firebase_admin, optionally slow to initialise."""
    sentinel = object()

    def initialize_app(cred, options):
        if calls is not None:
            calls.append(options)
        time.sleep(delay)
        return sentinel

    fake = types.ModuleType("firebase_admin")
    fake.initialize_app = initialize_app
    fake.get_app = lambda: sentinel
    monkeypatch.setitem(sys.modules, "firebase_admin", fake)
    monkeypatch.setattr(firebaseApp, "_credential", lambda: None)
    return sentinel


def test_the_app_is_built_once_and_reused(firebaseApp, monkeypatch):
    calls = []
    sentinel = _fakeFirebaseAdmin(monkeypatch, firebaseApp, calls=calls)

    assert firebaseApp.getFirebaseApp() is sentinel
    assert firebaseApp.getFirebaseApp() is sentinel
    assert len(calls) == 1


def test_a_concurrent_cold_start_waits_instead_of_refusing(firebaseApp, monkeypatch):
    """The bug this guards: `_tried` was set before `initialize_app` returned,
    so a request arriving mid-initialisation got None — which reaches the caller
    as 503 AUTH_UNAVAILABLE, on a perfectly healthy deployment."""
    calls = []
    sentinel = _fakeFirebaseAdmin(monkeypatch, firebaseApp, delay=0.15, calls=calls)

    results = []

    def call():
        results.append(firebaseApp.getFirebaseApp())

    threads = [threading.Thread(target=call) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results == [sentinel] * 5, "no caller may be told the app is unavailable"
    assert len(calls) == 1, "and it is still only built once"


def test_a_failed_initialisation_is_not_retried_per_request(firebaseApp, monkeypatch):
    calls = []

    def initialize_app(cred, options):
        calls.append(options)
        raise RuntimeError("bad credential")

    def get_app():
        raise RuntimeError("no app")

    fake = types.ModuleType("firebase_admin")
    fake.initialize_app = initialize_app
    fake.get_app = get_app
    monkeypatch.setitem(sys.modules, "firebase_admin", fake)
    monkeypatch.setattr(firebaseApp, "_credential", lambda: None)

    assert firebaseApp.getFirebaseApp() is None
    assert firebaseApp.getFirebaseApp() is None
    assert len(calls) == 1


def test_no_configuration_at_all_returns_none(firebaseApp, monkeypatch):
    monkeypatch.setattr(firebaseApp, "isEmulated", lambda: False)
    monkeypatch.setattr(firebaseApp, "_credential", lambda: None)

    assert firebaseApp.getFirebaseApp() is None
