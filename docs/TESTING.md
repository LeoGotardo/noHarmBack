# Testing Guide

## Overview

Zero tests exist. This doc covers setup, strategy, and full test inventory.

Architecture: `Route → Service → Repository → DB`. Test each layer in isolation (unit) and together (integration).

---

## Setup

### 1. Install dependencies

```bash
pip install pytest pytest-asyncio httpx pytest-mock factory-boy faker
```

Add to `requirements.txt`:
```
pytest==8.3.5
pytest-asyncio==0.25.3
httpx==0.28.1
pytest-mock==3.14.0
factory-boy==3.3.3
faker==37.0.0
```

### 2. pytest configuration

Create `pytest.ini` at project root:
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

### 3. Directory layout

```
tests/
├── conftest.py              # shared fixtures
├── unit/
│   ├── services/
│   │   ├── test_authService.py
│   │   ├── test_userService.py
│   │   ├── test_streakService.py
│   │   ├── test_friendshipService.py
│   │   ├── test_chatService.py
│   │   ├── test_messageService.py
│   │   └── test_badgeService.py
│   └── security/
│       ├── test_jwtHandler.py
│       ├── test_encryption.py
│       ├── test_rateLimiter.py
│       └── test_sanitizer.py
├── integration/
│   ├── routes/
│   │   ├── test_authRoutes.py
│   │   ├── test_userRoutes.py
│   │   ├── test_streakRoutes.py
│   │   ├── test_friendshipRoutes.py
│   │   ├── test_chatRoutes.py
│   │   ├── test_messageRoutes.py
│   │   └── test_badgesRoutes.py
│   └── repositories/
│       ├── test_userRepository.py
│       └── test_streakRepository.py
└── factories/
    ├── userFactory.py
    ├── streakFactory.py
    └── friendshipFactory.py
```

### 4. Core fixtures (`tests/conftest.py`)

```python
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from src.main import app

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def mock_db():
    return MagicMock()

@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = "user-uuid-1"
    user.username = "testuser"
    user.email = "test@example.com"
    user.status = 1  # enabled
    return user

@pytest.fixture
def valid_access_token(mock_user):
    from src.security.jwtHandler import JwtHandler
    handler = JwtHandler()
    return handler.createAccessToken(mock_user.id)
```

---

## Unit Tests — Services

Services take repositories as constructor args. Mock the repos, test business logic.

```python
# Pattern for every service test
from unittest.mock import MagicMock, patch
from src.domain.services.userService import UserService

def test_example(mock_db):
    repo = MagicMock()
    service = UserService(db=mock_db)
    service.userRepository = repo  # inject mock
```

---

### `test_authService.py`

| Test | What to verify |
|------|----------------|
| `test_login_success` | Returns access + refresh tokens on valid credentials |
| `test_login_wrong_password` | Raises `NoHarmException` with 401 |
| `test_login_user_not_found` | Raises `NoHarmException` with 404 |
| `test_login_rate_limit_triggers` | After 5 failed attempts, raises 429 |
| `test_login_blocked_user` | Status=3 raises 403 |
| `test_refresh_valid_token` | Returns new token pair, revokes old refresh token |
| `test_refresh_blacklisted_token` | Raises 401 |
| `test_refresh_expired_token` | Raises 401 |
| `test_logout_revokes_both_tokens` | Both JTIs added to blacklist |
| `test_audit_log_created_on_login` | `auditLogsRepository.create` called once |

---

### `test_userService.py`

| Test | What to verify |
|------|----------------|
| `test_findById_exists` | Returns `User` entity |
| `test_findById_not_found` | Raises 404 `NoHarmException` |
| `test_findByEmail_exists` | Returns `User` entity |
| `test_getPublicProfile_blocked` | Raises 403 when friendship.status=blocked |
| `test_getPublicProfile_self` | Returns own profile regardless of friendship |
| `test_updateProfile_username_taken` | Raises 409 |
| `test_updateProfile_success` | Returns updated `User` |
| `test_delete_self` | Marks soft-delete, returns True |
| `test_delete_not_owner` | Raises 403 |
| `test_updateStatus_admin` | Updates status, no ownership required |

---

### `test_streakService.py`

| Test | What to verify |
|------|----------------|
| `test_getCurrentByUserId_active` | Returns streak when `updated_at` < 24h |
| `test_getCurrentByUserId_expired` | Calls `_expireAndReset`, returns new streak |
| `test_getCurrentByUserId_none` | Raises 404 |
| `test_startStreak_success` | Creates streak, returns it |
| `test_startStreak_already_active` | Raises 409 |
| `test_endStreak_becomes_record` | Calls `markAsRecord` when duration > current record |
| `test_endStreak_no_active` | Raises 404 |
| `test_checkin_refreshes_timestamp` | Calls repository update |
| `test_durationDays_calculation` | Correct day math with known dates |

---

### `test_friendshipService.py`

| Test | What to verify |
|------|----------------|
| `test_sendRequest_success` | Creates friendship with status=pending |
| `test_sendRequest_self` | Raises 400 (no self-friending) |
| `test_sendRequest_duplicate` | Raises 409 if friendship exists |
| `test_sendRequest_blocked` | Raises 403 if blocked relationship exists |
| `test_accept_by_receiver` | status → accepted |
| `test_accept_by_sender` | Raises 403 |
| `test_accept_not_pending` | Raises 400 |
| `test_reject_by_receiver` | status → ignored |
| `test_reject_by_sender` | Raises 403 |
| `test_block_by_either_participant` | Both sender and receiver can block |
| `test_unblock_restores_disabled` | status → disabled |
| `test_delete_by_non_participant` | Raises 403 |

---

### `test_chatService.py`

| Test | What to verify |
|------|----------------|
| `test_getOrCreate_new_chat` | Creates pending chat |
| `test_getOrCreate_existing` | Returns existing chat without duplicate |
| `test_get_non_participant` | Raises 403 |
| `test_activate_pending` | status → enabled |
| `test_activate_already_active` | Raises 400 |
| `test_endChat_by_participant` | status → disabled |
| `test_endChat_non_participant` | Raises 403 |
| `test_delete_soft` | Marks deleted_at |

---

### `test_messageService.py`

| Test | What to verify |
|------|----------------|
| `test_sendMessage_activates_pending_chat` | Calls `chatRepository.updateStatus` |
| `test_sendMessage_sanitizes_content` | Bleach sanitization applied |
| `test_sendMessage_empty_content` | Raises 400 |
| `test_markAsRead_idempotent` | Second call doesn't raise error |
| `test_markAsRead_non_participant` | Raises 403 |
| `test_markAllAsRead_participant_only` | Updates all unread, raises 403 for others |

---

## Unit Tests — Security

### `test_jwtHandler.py`

| Test | What to verify |
|------|----------------|
| `test_createAccessToken_structure` | Has `sub`, `jti`, `exp`, `type=access` claims |
| `test_createRefreshToken_structure` | Has `type=refresh`, 7-day exp |
| `test_verifyToken_valid` | Returns payload dict |
| `test_verifyToken_expired` | Raises 401 |
| `test_verifyToken_wrong_type` | Access token rejected as refresh and vice versa |
| `test_verifyToken_tampered` | Raises 401 on signature mismatch |
| `test_revokeToken_blocks_reuse` | Revoked JTI raises 401 on next verify |
| `test_unique_jti_per_token` | Two tokens for same user have different JTIs |

---

### `test_encryption.py`

| Test | What to verify |
|------|----------------|
| `test_encrypt_decrypt_roundtrip` | `decrypt(encrypt(value)) == value` |
| `test_encrypt_produces_different_ciphertext` | Same input → different ciphertext (Fernet IV) |
| `test_hash_deterministic` | Same input → same SHA-256 hash |
| `test_hash_different_inputs` | Different inputs → different hashes |
| `test_argon2_verify_correct_password` | Returns True |
| `test_argon2_verify_wrong_password` | Returns False |

---

### `test_rateLimiter.py`

| Test | What to verify |
|------|----------------|
| `test_login_under_limit` | 4 failures → no lockout |
| `test_login_at_limit` | 5th failure → raises 429 with lockout duration |
| `test_login_lockout_resets` | After 30 min, attempts reset |
| `test_ip_limiter_blocks` | Exceed global IP limit → raises 429 |

---

### `test_sanitizer.py`

| Test | What to verify |
|------|----------------|
| `test_removes_script_tags` | `<script>` stripped |
| `test_removes_onclick` | Event handler attributes stripped |
| `test_preserves_plain_text` | Normal string unchanged |
| `test_preserves_safe_html` | If allowed tags configured, they survive |

---

## Integration Tests — Routes

Use `TestClient` + override FastAPI dependencies with mocks.

```python
from fastapi.testclient import TestClient
from src.main import app
from src.api.dependencies import getCurrentUser, getDbWithRLS

def override_get_current_user():
    return "user-uuid-1"

def override_get_db():
    return MagicMock()

app.dependency_overrides[getCurrentUser] = override_get_current_user
app.dependency_overrides[getDbWithRLS] = override_get_db

client = TestClient(app)
```

### `test_authRoutes.py`

| Test | Status code |
|------|-------------|
| `POST /auth/login` valid | 200 with token pair |
| `POST /auth/login` bad password | 401 |
| `POST /auth/login` 5th attempt | 429 |
| `POST /auth/refresh` valid | 200 with new tokens |
| `POST /auth/refresh` no header | 401 |
| `POST /auth/logout` valid | 204 |

### `test_userRoutes.py`

| Test | Status code |
|------|-------------|
| `GET /users/me` authenticated | 200 |
| `GET /users/me` no token | 401 |
| `PUT /users/me` valid body | 200 |
| `PUT /users/me` username taken | 409 |
| `GET /users/{userId}` blocked | 403 |
| `DELETE /users/me` | 204 |

### `test_streakRoutes.py`

| Test | Status code |
|------|-------------|
| `GET /streaks/current` active | 200 |
| `GET /streaks/current` none | 404 |
| `POST /streaks/start` success | 201 |
| `POST /streaks/start` duplicate | 409 |
| `POST /streaks/end` | 200 |
| `POST /streaks/checkin` | 200 |

### `test_friendshipRoutes.py`

| Test | Status code |
|------|-------------|
| `POST /friendships/{id}` send | 201 |
| `POST /friendships/{id}` self | 400 |
| `POST /friendships/{id}/accept` receiver | 200 |
| `POST /friendships/{id}/accept` sender | 403 |
| `POST /friendships/{id}/block` | 200 |
| `DELETE /friendships/{id}` non-participant | 403 |

### `test_chatRoutes.py`

| Test | Status code |
|------|-------------|
| `POST /chats` new chat | 201 |
| `POST /chats` existing | 200 |
| `GET /chats/{id}` non-participant | 403 |
| `POST /chats/{id}/accept` | 200 |
| `POST /chats/{id}/end` | 200 |

### `test_messageRoutes.py`

| Test | Status code |
|------|-------------|
| `POST /messages` valid | 201 |
| `POST /messages` empty content | 400 |
| `GET /messages/chat/{id}` participant | 200 |
| `PUT /messages/{id}/read` non-participant | 403 |
| `PUT /messages/chat/{id}/read` | 200 |

---

## Priority Order

Build in this order — each layer validates the one below:

1. **Security utilities** (`jwtHandler`, `encryption`) — foundation, no deps
2. **Service unit tests** — catch business logic bugs without DB
3. **Route integration tests** (auth first, user second) — validates full request cycle
4. **Repository integration tests** — only if test DB available; use a real Postgres instance

---

## Running Tests

```bash
# All tests
pytest

# One file
pytest tests/unit/services/test_authService.py

# One test
pytest tests/unit/services/test_authService.py::test_login_success

# With coverage
pip install pytest-cov
pytest --cov=src --cov-report=term-missing

# Verbose
pytest -v
```

---

## Coverage Targets

| Layer | Target |
|-------|--------|
| Security utilities | 95%+ |
| Services | 85%+ |
| Routes | 75%+ |
| Repositories | 60%+ (requires test DB) |
