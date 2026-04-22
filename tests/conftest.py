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
    "ENCRYPTION_KEY": "test-encryption-key-for-noharm-32b",
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


@pytest.fixture(autouse=True)
def patch_orm_models():
    """
    Patch ORM model constructors used inside service methods.

    Services instantiate ORM models (StreakModel, MessageModel, …) to create
    new DB rows. SQLAlchemy mapper initialisation fails in the test environment
    because of the known UserBadgesModel relationship bug in the codebase.
    Patching the model names in each service module prevents that error while
    still letting the service logic run normally.
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
