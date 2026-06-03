"""
Integration test setup.

Requirements:
    TEST_DATABASE_URL=postgresql://user:pass@localhost/noharm_test
    TEST_REDIS_URL=redis://localhost:6379/1   (optional — defaults to DB 1)

The test DB must have all Alembic migrations applied and the RLS helper
function set_current_user_id() installed.  Redis must be reachable.

Run:
    TEST_DATABASE_URL=... pytest tests/integration/ -v
"""

import os
import sys
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from fastapi import Depends
from fastapi.testclient import TestClient

# ── Skip whole module when env var is absent ──────────────────────────────────
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
TEST_REDIS_URL = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/1")

if not TEST_DATABASE_URL:
    pytest.skip(
        "Set TEST_DATABASE_URL to run integration tests. "
        "Example: TEST_DATABASE_URL=postgresql://u:p@localhost/noharm_test",
        allow_module_level=True,
    )

# ── Ensure src/ and the integration test dir are on path ─────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))  # makes helpers.py importable

# ── Override env vars BEFORE any src module is imported ──────────────────────
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = TEST_REDIS_URL

# ── Build test engine (no sslmode=require) ────────────────────────────────────
_DB_URL = TEST_DATABASE_URL.replace("postgres://", "postgresql://", 1)
_engine = create_engine(_DB_URL, pool_pre_ping=True, echo=False)
_SessionFactory = sessionmaker(_engine, autocommit=False, autoflush=False)

# ── Import app AFTER engine is ready (core.database is mocked by root conftest)
from main import app  # noqa: E402
from api.dependencies.database import getDb, getDbWithRLS  # noqa: E402
from api.dependencies.auth import getCurrentUser  # noqa: E402
from infrastructure.database.rlsContext import RLSContext  # noqa: E402


# ── Override the root-conftest autouse fixture (unit-test only) ───────────────
@pytest.fixture(autouse=True)
def patch_orm_models():
    """No-op for integration tests — real ORM models are used."""
    yield


# ── Wipe tables before every test ─────────────────────────────────────────────
@pytest.fixture(autouse=True)
def clean_tables():
    with _engine.connect() as conn:
        conn.execute(text("TRUNCATE tb_0, tb_5 CASCADE"))
        conn.commit()
    yield


# ── Reset in-memory rate limiters between tests ───────────────────────────────
@pytest.fixture(autouse=True)
def reset_rate_limiters():
    from security.middleware import _ipLimiter
    _ipLimiter._windows.clear()
    _ipLimiter._blocked.clear()
    # Reset the slowapi per-route limiter (shared global instance)
    from security.limiter import limiter
    try:
        limiter.reset()
    except Exception:
        pass
    # Flush the test Redis DB so no stale JTI or WS keys bleed between tests
    import redis as _redis
    r = _redis.from_url(TEST_REDIS_URL, decode_responses=True)
    r.flushdb()
    yield
    r.flushdb()


# ── DB proxy: gives repositories the Database interface they expect ────────────
class _DbProxy:
    """Repositories call self.db.session and self.db.engine.
    This wrapper satisfies that interface using a single real test Session."""
    def __init__(self, session: Session):
        self._session = session
        self.engine = _engine

    @property
    def session(self) -> Session:
        return self._session


# ── FastAPI test client with real DB sessions ─────────────────────────────────
@pytest.fixture
def client():
    def _get_db():
        session = _SessionFactory()
        try:
            yield _DbProxy(session)
        finally:
            session.close()

    def _get_db_with_rls(userId: str = Depends(getCurrentUser)):
        session = _SessionFactory()
        try:
            try:
                RLSContext.setUserId(session, userId)
            except Exception:
                pass
            yield _DbProxy(session)
        finally:
            session.close()

    app.dependency_overrides[getDb] = _get_db
    app.dependency_overrides[getDbWithRLS] = _get_db_with_rls

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


# ── Auth helpers ──────────────────────────────────────────────────────────────
def _new_user_payload():
    uid = str(uuid.uuid4())
    return {
        "uid": uid,
        "email": f"test_{uid[:8]}@example.com",
        "username": f"user_{uid[:8]}",
        "emailVerified": True,
        "photoURL": None,
    }


def _register(client, payload=None):
    payload = payload or _new_user_payload()
    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    tokens = resp.json()
    return {
        "payload": payload,
        "uid": payload["uid"],
        "access": tokens["accessToken"],
        "refresh": tokens["refreshToken"],
        "headers": {"Authorization": f"Bearer {tokens['accessToken']}"},
    }


@pytest.fixture
def user_a(client):
    return _register(client)


@pytest.fixture
def user_b(client):
    return _register(client)


# ── Direct JWT factory (for WS tests that don't touch the DB) ─────────────────
@pytest.fixture(scope="session")
def jwt_factory():
    from security.jwtHandler import JwtHandler
    from security.tokenBlacklist import TokenBlacklist
    import redis as _redis

    r = _redis.from_url(TEST_REDIS_URL, decode_responses=True)
    bl = TokenBlacklist.__new__(TokenBlacklist)
    bl._redis = r
    jh = JwtHandler(bl)
    return jh


# ── Friendship helper ─────────────────────────────────────────────────────────
def _make_friends(client, a, b):
    """Send + accept a friend request between user_a and user_b."""
    resp = client.post(f"/friendships/{b['uid']}", headers=a["headers"])
    assert resp.status_code == 201, resp.text
    fid = resp.json()["id"]
    resp = client.post(f"/friendships/{fid}/accept", headers=b["headers"])
    assert resp.status_code == 200, resp.text
    return fid
