"""Unit tests for the database session dependencies.

`getDbWithRLS` is the reason a route can look unauthenticated and still be
safe: it depends on `getCurrentUser` itself, so FastAPI resolves the token
before the handler runs even when the handler never asks for the user id. That
is load-bearing and nothing covered it — `api/dependencies/database.py` sat at
50%.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.dependencies.auth import getCurrentUser
from api.dependencies.database import getDb, getDbWithRLS


def _build_app(dependency):
    app = FastAPI()

    @app.get("/thing")
    def thing(db=Depends(dependency)):
        return {"ok": True}

    return app


@pytest.fixture
def fake_database():
    session = MagicMock()
    db = MagicMock()
    db.session = session
    db.engine = MagicMock()
    with patch("api.dependencies.database.database", db):
        yield session


# ── getDbWithRLS carries the authentication requirement ───────────────────────

def test_getDbWithRLS_requires_a_token_even_without_getCurrentUser(fake_database):
    """A route that only asks for the session is still gated on the token."""
    client = TestClient(_build_app(getDbWithRLS), raise_server_exceptions=False)
    assert client.get("/thing").status_code in (401, 403)


def test_getDbWithRLS_sets_the_rls_context_to_the_caller(fake_database):
    app = _build_app(getDbWithRLS)
    app.dependency_overrides[getCurrentUser] = lambda: "uid-42"
    with patch("api.dependencies.database.RLSContext") as rls:
        TestClient(app).get("/thing")
    rls.setUserId.assert_called_once_with(fake_database, "uid-42")


def test_getDbWithRLS_closes_the_session(fake_database):
    app = _build_app(getDbWithRLS)
    app.dependency_overrides[getCurrentUser] = lambda: "uid-42"
    with patch("api.dependencies.database.RLSContext"):
        TestClient(app).get("/thing")
    fake_database.close.assert_called_once()


def test_getDbWithRLS_closes_the_session_when_the_handler_raises(fake_database):
    app = FastAPI()

    @app.get("/boom")
    def boom(db=Depends(getDbWithRLS)):
        raise RuntimeError("handler failed")

    app.dependency_overrides[getCurrentUser] = lambda: "uid-42"
    with patch("api.dependencies.database.RLSContext"):
        TestClient(app, raise_server_exceptions=False).get("/boom")
    fake_database.close.assert_called_once()


# ── getDb is deliberately unauthenticated ─────────────────────────────────────

def test_getDb_does_not_require_a_token(fake_database):
    """Public endpoints (register, login) use it — it must not gate on auth."""
    client = TestClient(_build_app(getDb))
    assert client.get("/thing").status_code == 200


def test_getDb_sets_no_rls_context(fake_database):
    """No context means no row filtering — the reason it is public-only."""
    with patch("api.dependencies.database.RLSContext") as rls:
        TestClient(_build_app(getDb)).get("/thing")
    rls.setUserId.assert_not_called()


def test_getDb_closes_the_session(fake_database):
    TestClient(_build_app(getDb)).get("/thing")
    fake_database.close.assert_called_once()


def test_proxy_exposes_the_session_and_engine_repositories_expect(fake_database):
    from api.dependencies.database import _DbProxy
    proxy = _DbProxy(fake_database)
    assert proxy.session is fake_database
    assert proxy.engine is not None
