"""
Integration test setup.

Requirements:
    TEST_DATABASE_URL=postgresql://user:pass@localhost/noharm_test
    TEST_REDIS_URL=redis://localhost:6379/1   (optional — defaults to DB 1)

The test DB must have all Alembic migrations applied, including the RLS
policies. No helper function is needed — RLSContext sets the session variable
with `SELECT set_config('app.current_user_id', ...)`. Redis must be reachable.

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


# ── Reset rate limiter state between tests ────────────────────────────────────
@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """Both limiters keep their state in Redis, so flushing the test DB clears
    the sliding windows (`rl:ip:*`), the login lockouts (`rl:login:*`), the JTI
    blacklist (`jti:*`) and the WS counters (`ws:*`) in one go.

    This used to clear `_ipLimiter._windows` and `._blocked` instead. Those
    attributes disappeared when IpRateLimiter moved off in-process dicts, so
    the fixture raised AttributeError before every single test and the whole
    integration suite was unrunnable.
    """
    import redis as _redis
    r = _redis.from_url(TEST_REDIS_URL, decode_responses=True)
    r.flushdb()

    # The slowapi limiter keeps its own `LIMITS:` keys; reset() also covers the
    # in-memory fallback it uses when Redis was unreachable at import time.
    from security.limiter import limiter
    try:
        limiter.reset()
    except Exception:
        pass

    yield
    r.flushdb()


# ── Real account-status lookups ───────────────────────────────────────────────
@pytest.fixture(autouse=True)
def real_account_status_lookups():
    """Point getAccountStatus at the test database.

    The root conftest swaps `core.database` for a MagicMock, and
    `api.dependencies.auth` imported the `database` singleton from it. The
    status query therefore returned a MagicMock — never None, never a rejected
    status — so §1.4 (a banned or deleted account must stop being able to use
    an already-issued token) passed vacuously here too, not just in the unit
    tests.
    """
    import api.dependencies.auth as authDeps

    class _RealDatabase:
        @property
        def session(self):
            return _SessionFactory()

        @property
        def engine(self):
            return _engine

    original = authDeps.database
    authDeps.database = _RealDatabase()
    try:
        yield
    finally:
        authDeps.database = original


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
# Defined once, in helpers.py. They used to be duplicated here with a leading
# underscore, and the two copies were already drifting apart.
from helpers import new_user_payload as _new_user_payload, register as _register  # noqa: E402


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
from helpers import make_friends as _make_friends  # noqa: E402,F401
