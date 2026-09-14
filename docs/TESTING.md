# Testing Guide

## Overview

**905 unit tests implemented — 0 failures** (plus 3 xfailed). 196 integration tests.

Integration tests truncate `tb_0` and `tb_5` (cascading to everything else)
before each test *and once when the session ends* — otherwise the last test's
accounts, reports and audit trail sat in the database until somebody ran the
suite again.

Architecture: `Route → Service → Repository → DB`. Each layer is tested in isolation with mocked dependencies.

```bash
pytest          # run all
pytest -v       # verbose
pytest -q       # quiet (dots only)
pytest --tb=short  # short tracebacks on failure
```

---

## Setup

Dependencies already installed and configured. To reinstall:

```bash
pip install pytest pytest-asyncio httpx pytest-mock
```

`pytest.ini` is configured at the project root:

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

`src/` is added to `sys.path` automatically by `tests/conftest.py` — no `src.` prefix needed in imports.

---

## Directory Layout

```
tests/
├── conftest.py                          # shared fixtures + sys.path + env + DB mock
├── unit/
│   ├── dependencies/
│   │   └── test_auth.py                 ✅ getCurrentUser dependency
│   ├── exceptions/
│   │   └── test_exceptions.py           ✅ NoHarmException + database exceptions
│   ├── repositories/
│   │   ├── test_auditLogsRepository.py  ✅
│   │   ├── test_badgeRepository.py      ✅
│   │   ├── test_chatRepository.py       ✅
│   │   ├── test_friendshipRepository.py ✅
│   │   ├── test_messageRepository.py    ✅
│   │   ├── test_streakRepository.py     ✅
│   │   ├── test_userBadgesRepository.py ✅
│   │   └── test_userRepository.py       ✅
│   ├── routes/
│   │   ├── test_authRoutes.py           ✅
│   │   ├── test_friendshipRoutes.py     ✅
│   │   ├── test_reportRoutes.py         ✅
│   │   ├── test_streakRoutes.py         ✅
│   │   └── test_userRoutes.py           ✅
│   ├── schemas/
│   │   └── test_schemas.py              ✅ all Pydantic DTOs
│   ├── infrastructure/
│   │   └── test_firebaseApp.py          ✅ one app per process, cold-start race
│   ├── jobs/
│   │   ├── test_purgeAccounts.py        ✅
│   │   └── test_purgeEvidence.py        ✅ evidence retention sweep
│   ├── security/
│   │   ├── test_encryption.py           ✅
│   │   ├── test_jwtHandler.py           ✅
│   │   ├── test_middleware.py           ✅
│   │   ├── test_persistentHashTable.py  ✅
│   │   ├── test_rateLimiter.py          ✅
│   │   ├── test_sanitizer.py            ✅
│   │   └── test_tokenBlacklist.py       ✅
│   └── services/
│       ├── test_auditLogsService.py     ✅
│       ├── test_authService.py          ✅
│       ├── test_badgeService.py         ✅
│       ├── test_chatService.py          ✅
│       ├── test_friendshipService.py    ✅
│       ├── test_messageService.py       ✅
│       ├── test_noticeService.py        ✅
│       ├── test_reportService.py        ✅
│       ├── test_streakService.py        ✅
│       ├── test_userBadgeService.py     ✅
│       └── test_userService.py          ✅
└── integration/                     ✅ real Postgres + Redis, real HTTP
    ├── conftest.py                   (test engine, Firebase emulator mode)
    ├── helpers.py                    (identities, tokens, direct-SQL helpers)
    ├── test_accountLifecycle.py      ✅ deletion window, bans, admin gate, purge
    ├── test_auth.py                  ✅
    ├── test_badges.py / test_chat.py / test_friendship.py / test_message.py
    ├── test_reports.py                ✅ filing, duplicates, reporter-only reads
    ├── test_reportEvidence.py         ✅ capture, admin-only reads, surviving a purge, retention
    ├── test_moderationQueue.py        ✅ the review lock: claim, collision, expiry, release
    ├── test_suspensions.py            ✅ timed bans, the date in the refusal, lifting itself
    ├── test_notices.py                ✅ warnings, suspension notices, acknowledgement, what they never name
    ├── test_rls.py / test_security.py / test_streak.py
    ├── test_user.py / test_websocket.py
```

---

## conftest.py — Shared Fixtures

`tests/conftest.py` handles three things before any test runs:

1. **`sys.path`** — inserts `src/` so `from infrastructure...` imports resolve without prefix
2. **Env vars** — sets all required secrets (JWT keys, encryption key, DB URL) to safe test values
3. **DB mock** — replaces `core.database` in `sys.modules` before any module imports it, preventing real Postgres connections

### Shared fixtures

| Fixture | Scope | Description |
|---------|-------|-------------|
| `mock_db` | function | `MagicMock` with `.session` and `.engine` attributes |
| `mock_user` | function | `MagicMock` user with `id`, `username`, `email`, `status` |
| `patch_orm_models` | function (autouse) | Patches ORM constructors in service modules to prevent SQLAlchemy mapper errors |

---

## Test Patterns

### Repository tests

Each repository test file has its own `session`, `db`, and `repo` fixtures. The session is a `MagicMock` whose query chain is pre-configured.

```python
@pytest.fixture
def session():
    s = MagicMock()
    s.query.return_value.filter.return_value.first.return_value = None
    return s

@pytest.fixture
def repo(db):
    with patch("infrastructure.database.repositories.userRepository.UserModel"):
        from infrastructure.database.repositories.userRepository import UserRepository
        return UserRepository(db)
```

### Service tests

Services take a `db` argument. After construction, replace individual repositories with `MagicMock`:

```python
def _make_service(mock_db):
    service = UserService(db=mock_db)
    service.userRepository = MagicMock()
    service.friendshipRepository = MagicMock()
    return service
```

### Route tests

Routes are tested by importing the router, creating a small `FastAPI` test app, and using `TestClient`. Dependencies (`getCurrentUser`, `getDbWithRLS`) are overridden:

```python
app = FastAPI()
app.include_router(router)
app.dependency_overrides[getCurrentUser] = lambda: "test-user-id"
client = TestClient(app)
```

---

## What Is Tested

### Security (`tests/unit/security/`)

| File | Coverage |
|------|----------|
| `test_encryption.py` | AES-256 encrypt/decrypt roundtrip, SHA-256 hash determinism, Argon2 verify |
| `test_jwtHandler.py` | Token creation, expiry, type enforcement, blacklist integration, JTI uniqueness |
| `test_tokenBlacklist.py` | Add/check/expiry behaviour, file persistence |
| `test_persistentHashTable.py` | Append, lookup, compaction |
| `test_rateLimiter.py` | Login lockout (5 attempts), IP block, window reset |
| `test_sanitizer.py` | Script tag removal, attribute stripping, plain text passthrough |
| `test_middleware.py` | Security headers presence, rate limit middleware response |

### Exceptions (`tests/unit/exceptions/`)

| File | Coverage |
|------|----------|
| `test_exceptions.py` | `NoHarmException` defaults and `toDict()`, `NoEngineException`, `NoSessionException`, `NoDatabaseParameterException` |

### Repositories (`tests/unit/repositories/`)

Every repository is tested for:
- `findById` — success, not-found 404, DB error 500
- All find variants (by type, by date range, by user, etc.) — empty list, paginated, DB error 500
- `create` — success, rollback on DB error
- `update` / `updateStatus` / `softDelete` — success, not-found 404, DB error 500
- Method-specific logic (e.g. `grant` existing vs. new badge, `markAsRecord`)

### Services (`tests/unit/services/`)

| File | Key scenarios |
|------|---------------|
| `test_authService.py` | Login success/failure, rate limit, banned/blocked/deleted account, refresh rotation, logout blacklist |
| `test_userService.py` | Profile access (blocked 403, self, no-friendship), update validation, soft delete ownership |
| `test_streakService.py` | Active streak, start/end/checkin, last_checkin update, record detection |
| `test_friendshipService.py` | Send (self/duplicate/blocked), accept/reject (receiver-only), block, delete |
| `test_chatService.py` | Create, activate, end, participant check, soft delete |
| `test_messageService.py` | Send (empty content, non-participant, pending chat), markAsRead, markAllAsRead |
| `test_badgeService.py` | Grant and list |
| `test_userBadgeService.py` | Association management |
| `test_reportService.py` | Report self/unknown reason/deleted account, duplicate while open, sanitised details, admin resolution, evidence capture (profile + both sides of a named chat), a chat the reporter is not in refused before anything is filed, a capture failure never failing the report, audited evidence reads, the review lock (claim/release/resolve, collisions, stale locks) |
| `test_noticeService.py` | Warnings (conduct named, reporter never), `self_harm` refused with the crisis-resources reason, self-warning, deleted accounts, suspension notices that never undo the suspension, acknowledgement being the recipient's only |
| `test_auditLogsService.py` | Paginated queries, create |

### Routes (`tests/unit/routes/`)

| File | Endpoints covered |
|------|------------------|
| `test_authRoutes.py` | POST /auth/register, /auth/login, /auth/refresh, /auth/logout |
| `test_userRoutes.py` | GET /users/me, PUT /users/me, GET /users/{id}, DELETE /users/me, and the admin gate on PUT /users/{id}/status/{status} and PUT /users/{id}/suspend |
| `test_streakRoutes.py` | GET /streaks/current, /streaks/record, /streaks/history, POST /streaks/start, /streaks/end, /streaks/checkin |
| `test_friendshipRoutes.py` | POST /friendships, PUT /friendships/{id}/accept, /reject, /block, DELETE /friendships/{id} |
| `test_reportRoutes.py` | POST /reports/{userId} (including `chatId` forwarding and the refusal of any body field carrying message text), GET /reports/mine (which never names the reviewing moderator), and the admin gate on GET /reports, GET /reports/{id}/evidence, POST/DELETE /reports/{id}/claim and PUT /reports/{id}/resolve/{status} |

### Schemas (`tests/unit/schemas/`)

Covers all Pydantic DTOs — required fields, optional fields, validation errors, nested types, `model_config` enforcement.

---

## Not Yet Implemented

| Gap | Priority |
|-----|----------|
| `tests/unit/routes/test_chatRoutes.py` | Medium |
| `tests/unit/routes/test_messageRoutes.py` | Medium |
| `tests/unit/routes/test_badgesRoutes.py` | Low |
| `tests/unit/routes/test_auditLogsRoutes.py` | Low |
| `tests/integration/` — green (122 passed, 17 skipped; 139 passed with `RLS_TEST_DATABASE_URL` on a NOBYPASSRLS role) | — the 17 skips are `test_rls.py` against a superuser role |

---

## Running Tests

```bash
# All tests
pytest

# One directory
pytest tests/unit/services/

# One file
pytest tests/unit/services/test_authService.py

# One test
pytest tests/unit/services/test_authService.py::test_login_success

# With coverage
pip install pytest-cov
pytest --cov=src --cov-report=term-missing

# Short tracebacks (recommended for CI)
pytest --tb=short -q
```

---

## Running the integration suite

It needs a real Postgres and a real Redis, and skips itself entirely when
`TEST_DATABASE_URL` is unset — so a plain `pytest` run is unit-only and silent
about it.

```bash
# 1. a database of its own, migrated to head
docker exec postgres_db psql -U root -d postgres -c 'CREATE DATABASE noharm_test;'
DATABASE_URL=postgresql://root:<pw>@localhost:5432/noharm_test \
DATABASE_URL_UNPOOLED=postgresql://root:<pw>@localhost:5432/noharm_test \
APP_ENV=alembic alembic upgrade head

# 2. run
TEST_DATABASE_URL=postgresql://root:<pw>@localhost:5432/noharm_test \
TEST_REDIS_URL=redis://localhost:6379/1 \
pytest tests/integration -q
```

Two things that will otherwise waste an afternoon:

- **`python-dateutil` must actually be installed.** It is in `requirements.txt`,
  but a venv built before it was added still runs the unit suite fine and fails
  every streak and message test with
  `ImproperlyConfigured: 'python-dateutil' is required to process datetimes` —
  a 500 from inside the encrypted DateTime column, which reads like a code bug.
- **`/health` is exempt from the IP rate limiter** (`_EXEMPT_PATHS`), so it can
  never be used to provoke a 429 — an orchestrator that gets one from a health
  check restarts the container. `test_security.py` drives `/users/me` instead.
- **The RLS tests skip against a superuser.** `root` on a stock Postgres image
  bypasses every policy, so `test_rls.py` skips rather than passing vacuously.
  Point `RLS_TEST_DATABASE_URL` at a NOSUPERUSER, NOBYPASSRLS role to run them.

`tests/conftest.py` pins `FIREBASE_SERVICE_ACCOUNT`, `FIREBASE_SERVICE_ACCOUNT_PATH`
and `FIREBASE_PROJECT_ID` to empty/`demo-noharm` for the same reason it pins
`APP_ENV=test`: `core.config` copies `.secrets.toml`'s `[default]` section into
`os.environ` for anything not already set, and it is imported by that conftest.
Without the pins, a developer with a real service account in `.secrets.toml`
gets Firebase initialised against the live project, every locally minted token
rejected, and 47 collection errors that do not reproduce anywhere else.

## Coverage Targets

| Layer | Current State | Target |
|-------|--------------|--------|
| Security utilities | Implemented | 95%+ |
| Services | Implemented | 85%+ |
| Repositories | Implemented | 80%+ |
| Routes | Partial (4/9 files) | 75%+ |
| Integration | Implemented and green | — |
