"""
Root conftest — runs before any test file is imported.

Responsibilities:
  1. Add src/ to sys.path so tests can import from src without the 'src.' prefix
  2. Set all required env vars before config.py is first imported
  3. Mock core.database in sys.modules to prevent real DB connections
"""

import sys
import os
import tempfile
from unittest.mock import MagicMock

# ── 1. Path setup ─────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── 2. Env vars (must be set before core.config is imported) ──────────────────
_test_storage = tempfile.mkdtemp(prefix="noharm_test_")

_STATUS_CODES = (
    '{"disabled":0,"enabled":1,"deleted":2,"blocked":3,'
    '"pending":4,"accepted":5,"ignored":6,"unread":7,"read":8,"banned":9}'
)

_DEFAULTS = {
    # APP_ENV defaults to "prod", which made the suite read the developer's
    # .secrets.toml [prod] section for anything missing below. Pinning a section
    # that does not exist keeps the tests self-contained: whatever is not in
    # _DEFAULTS fails loudly here instead of silently picking up real values.
    "APP_ENV": "test",
    "ENCRYPTION_KEY": "test-encryption-key-for-noharm-32b",
    "DATABASE_ENCRYPTION_KEY": "test-database-encryption-key-32by",
    # Distinct from DATABASE_ENCRYPTION_KEY on purpose — reusing that value here
    # would let a test pass that never checks the two are separate keys.
    "BLIND_INDEX_KEY": "test-blind-index-key-for-unit-tests",
    "DATABASE_URL": "postgresql://test:test@localhost/testdb",
    "DATABASE_HOST": "localhost",
    "DATABASE_NAME": "testdb",
    "DATABASE_USER": "test",
    "DATABASE_PASSWORD": "test",
    "DATABASE_URL_UNPOOLED": "postgresql://test:test@localhost/testdb",
    "STORAGE_SERVICE_URI": "http://localhost",
    "STORAGE_SERVICE_KEY": "test-storage-key",
    "EXEC_MODE": "test",
    "DEBUG": "false",
    "PORT": "8000",
    "STATUS_CODES": _STATUS_CODES,
    "JWT_SECRET_KEY": "test-jwt-secret-key-for-unit-testing",
    "JWT_REFRESH_SECRET_KEY": "test-jwt-refresh-secret-key-testing",
    "JWT_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "15",
    "REFRESH_TOKEN_EXPIRE_DAYS": "7",
    "STORAGE_PATH": _test_storage,
    "ALLOWED_ORIGINS": '["http://localhost:3000"]',
    # DB 15, never DB 0: security/limiter.py builds a Redis-backed slowapi
    # limiter at import time, so the suite writes real rate-limit counters.
    # Pointing them at a scratch DB keeps the developer's dev Redis intact.
    "REDIS_URL": "redis://localhost:6379/15",
    "TRUSTED_PROXIES": "[]",
    # Not optional despite being empty, and not shadowable from the integration
    # conftest: config.py copies `.secrets.toml`'s [default] section into
    # os.environ for any key not already present, FIREBASE_SERVICE_ACCOUNT
    # lives in [default], and this file imports `core.config` below — so by the
    # time any other conftest runs, the real credential is already in the
    # environment and the singleton is already built around it. The integration
    # suite then initialises Firebase against the real project and rejects
    # every token it mints for `demo-noharm`, which read as 47 collection
    # errors on a developer machine and nothing at all on a clean one.
    # Claiming the keys here, before the import, is the only place that works.
    "FIREBASE_SERVICE_ACCOUNT": "",
    "FIREBASE_SERVICE_ACCOUNT_PATH": "",
    "FIREBASE_PROJECT_ID": "demo-noharm",
}

for _key, _val in _DEFAULTS.items():
    os.environ.setdefault(_key, _val)

# ── 3. Mock core.database before any src module is imported ───────────────────
# database.py calls Database() at module level, which tries to connect to Postgres.
# Replacing it in sys.modules prevents that entirely.
_mock_db_module = MagicMock()
_mock_db_module.Database = MagicMock
_mock_db_module.database = MagicMock()
sys.modules["core.database"] = _mock_db_module


# ── Shared fixtures ───────────────────────────────────────────────────────────
import pytest
from unittest.mock import patch
from core.config import config


@pytest.fixture
def mock_db():
    """Mock database instance passed to services."""
    db = MagicMock()
    db.session = MagicMock()
    db.engine = MagicMock()
    return db


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = "user-uid-001"
    user.username = "testuser"
    user.email = "test@example.com"
    user.status = config.STATUS_CODES["enabled"]
    user.profile_picture = b""
    return user


@pytest.fixture
def patch_orm_models():
    """Replace the ORM constructors a service calls with mocks.

    Opt in only when a test needs to assert on *how* a model was constructed —
    `StreakModel.call_args.kwargs["start_at"]` and the like. Everything else
    runs against the real classes.

    It used to be autouse, to work around mapper initialisation failing with
    "expression 'UserBadgesModel.user_id' failed to locate a name". That was
    never a bug in the models: `UserModel` declares its relationship as a
    string, and the class it names only reaches SQLAlchemy's registry when its
    module is imported. `models/__init__.py` now imports all ten, so the
    failure is gone and 757 of the 758 unit tests exercise the real
    constructors — which is what they were written to do.
    """
    targets = [
        "domain.services.streakService.StreakModel",
        "domain.services.streakService.AuditLogsModel",
        "domain.services.messageService.MessageModel",
        "domain.services.authService.UserModel",
        "domain.services.authService.AuditLogsModel",
        "domain.services.userService.AuditLogsModel",
        "domain.services.chatService.ChatModel",
        "domain.services.friendshipService.FriendshipModel",
    ]

    patches = [patch(t) for t in targets]
    mocks = [p.start() for p in patches]

    # Each mock returns a fresh MagicMock instance when called (default behavior)
    for m in mocks:
        m.return_value = MagicMock()

    yield

    for p in patches:
        p.stop()


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    """Drop every rate-limit counter between tests.

    `security/limiter.py` builds its slowapi Limiter at import time with
    `storage_uri=REDIS_URL`, so the per-route ceilings are backed by a real
    Redis and survive not just across tests but across whole pytest runs.
    Without this the suite passed once and then started returning 429 on route
    tests — green or red depended on how recently it had last been run.

    Tolerant of Redis being unreachable: the limiter degrades to in-memory
    storage there, and `reset()` still clears that.
    """
    try:
        from security.limiter import limiter
        limiter.reset()
    except Exception:
        pass

    # The middleware's IpRateLimiter, the login lockout, the JTI blacklist and
    # the WS counters all live in the same Redis. REDIS_URL is pinned to a
    # scratch DB above, so wiping it wholesale is the cheapest way to give each
    # test a clean slate.
    try:
        import redis
        from core.config import config
        redis.from_url(config.REDIS_URL).flushdb()
    except Exception:
        pass

    yield
