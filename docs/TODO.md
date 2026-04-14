# NoHarm Backend — Implementation Plan

This document tracks the current state of the backend, architectural decisions, and the ordered implementation plan.

---

## Current State

### What is done

| Layer | Status |
|-------|--------|
| Project structure (Clean Architecture) | ✅ Complete |
| Core config (`Dynaconf`, multi-environment) | ✅ Complete |
| Database engine + session (`SQLAlchemy`) | ✅ Complete |
| Alembic migrations setup | ✅ Complete |
| Vercel + Neon deployment config | ✅ Complete |
| All SQLAlchemy models (8 tables) | ✅ Complete |
| Field-level AES-256 encryption on all sensitive columns | ✅ Complete |
| All repositories (8 files, full CRUD) | ✅ Complete |
| `Encryption` utility (Fernet + Argon2 + SHA-256) | ✅ Complete |
| `JwtHandler` (access + refresh, per-type secrets) | ✅ Complete |
| `TokenBlacklist` (persistent JSONL, hashed JTIs) | ✅ Complete |
| `PersistentHashTable` (append-only O(1) log) | ✅ Complete |
| `IpRateLimiter` + `LoginRateLimiter` (sliding window) | ✅ Complete |
| `RateLimitMiddleware` + `SecurityHeadersMiddleware` | ✅ Complete |
| `Sanitizer` (HTML stripping via bleach) | ✅ Complete |
| `getCurrentUser` dependency (JWT → userId) | ✅ Complete |
| `getDb` dependency (session injection) | ✅ Complete |
| `NoHarmException` hierarchy | ✅ Complete |
| `main.py` (FastAPI app, CORS, middlewares, health check) | ✅ Complete |
| All Pydantic schemas (`userSchemas`, `streakSchemas`, `chatSchemas`, `badgeSchemas`) | ✅ Complete |
| All services (`userService`, `streakService`, `chatsService`, `badgeService`) | ✅ Complete |
| All routes (`authRoutes`, `userRoutes`, `streakRoutes`, `chatRoutes`, `badgesRoutes`) | ✅ Complete |
| WebSocket (`socketManager`, `chatHandlers`, `presenceHandlers`) | ✅ Complete  |

### What is missing

| Layer | Status |
|-------|--------|
| Storage service (file uploads) | ⬜ Empty |

---

## Architecture Decisions

### Why Clean Architecture?

The project separates concerns into four concentric layers:

```
Entities (domain/entities)
    ↑ used by
Services (domain/services)
    ↑ used by
Routes + Schemas (api)
    ↑ use
Repositories + Models (infrastructure)
```

**Benefits:**
- Services can be unit-tested by mocking repositories — no real database needed
- Swapping the database (e.g. PostgreSQL → MongoDB) only requires changing the repository layer
- Routes never contain business logic — they are thin HTTP adapters
- Pydantic schemas centralise validation and prevent mass assignment

### Why field-level encryption?

Standard database encryption (TDE, disk encryption) protects against physical theft of storage but not against a compromised database user or a SQL injection vulnerability. Field-level encryption ensures that even a full database dump exposes only ciphertext.

Trade-off: encrypted fields cannot be sorted, `LIKE` searched, or range-queried. The project mitigates this by storing a SHA-256 hash alongside each encrypted field for equality lookups.

### Why a file-based JWT blacklist instead of Redis?

Redis is the standard choice, but introduces an external dependency. The `PersistentHashTable` implementation covers the current scale:
- O(1) write cost per revocation (append only)
- Survives server restarts (file-backed)
- Automatic expiry cleanup on startup

The interface (`TokenBlacklist`) is decoupled — swapping to Redis requires only changing `tokenBlacklist.py`, with no changes to `JwtHandler` or any route.

### Why obfuscated table/column names?

Column names like `cl_0b` instead of `username` add a layer of obscurity on top of field-level encryption. An attacker who gains read access to the schema cannot immediately understand the data model.

---

## Implementation Plan

### Phase 1 — Schemas (unblocks everything else)

All schemas must be completed before services or routes can be written. Schemas define the contract between the HTTP layer and the business layer.

#### `src/schemas/userSchemas.py`

```python
# Input schemas
class UserRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    email: EmailStr
    password: str = Field(min_length=8)

class UserUpdateRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=30)
    profilePicture: Optional[bytes] = None

class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str

# Output schemas
class UserPublicResponse(BaseModel):      # returned to other users
    id: str
    username: str
    createdAt: datetime
    model_config = ConfigDict(from_attributes=True)

class UserPrivateResponse(BaseModel):     # returned to the owner
    id: str
    username: str
    email: str
    status: int
    createdAt: datetime
    model_config = ConfigDict(from_attributes=True)

class TokenResponse(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "Bearer"
```

#### `src/schemas/streakSchemas.py`

```python
class StreakResponse(BaseModel):
    id: str
    ownerId: str
    start: datetime
    end: Optional[datetime]
    status: int
    isRecord: bool
    createdAt: datetime
    model_config = ConfigDict(from_attributes=True)

class StreakResetRequest(BaseModel):
    note: Optional[str] = Field(None, max_length=500)
```

#### `src/schemas/chatSchemas.py`

```python
class MessageRequest(BaseModel):
    recipientId: str
    content: str = Field(min_length=1, max_length=2000)

class MessageResponse(BaseModel):
    id: str
    chatId: str
    senderId: str
    content: str
    status: int
    sendAt: datetime
    model_config = ConfigDict(from_attributes=True)

class ConversationResponse(BaseModel):
    chatId: str
    participantId: str
    messages: list[MessageResponse]
    status: int
```

#### `src/schemas/badgeSchemas.py`

```python
class BadgeResponse(BaseModel):
    id: str
    name: str
    description: str
    milestone: datetime
    status: int
    model_config = ConfigDict(from_attributes=True)

class BadgeListResponse(BaseModel):
    badges: list[BadgeResponse]
    total: int
```

---

### Phase 2 — Services (business logic)

#### `src/domain/services/userService.py`

Key methods to implement:

| Method | Business rules |
|--------|----------------|
| `registerUser(request)` | Check email uniqueness · Hash password (Argon2) · Create user with `status=enabled` |
| `loginUser(request)` | Find by email · Verify password · Issue access + refresh tokens · Call `loginRateLimiter.onSuccess()` on success |
| `refreshToken(refreshToken)` | Verify refresh token · Revoke old refresh token (blacklist) · Issue new token pair |
| `logoutUser(accessToken, refreshToken)` | Revoke both tokens |
| `getProfile(userId)` | Return `UserPrivateResponse` |
| `updateProfile(userId, request)` | Validate whitelisted fields · Persist changes |
| `changePassword(userId, oldPassword, newPassword)` | Verify old password · Hash new password · Revoke all tokens |

#### `src/domain/services/streakService.py`

| Method | Business rules |
|--------|----------------|
| `getCurrentStreak(userId)` | Find active streak · Check if expired (>24h since last update) · Auto-reset if expired |
| `createStreak(userId)` | Create streak with `start=now`, `status=enabled`, `isRecord=False` |
| `endStreak(userId)` | Set `end=now`, `status=disabled` · Check if new record · If record, `markAsRecord` · Create new streak |
| `getStreakHistory(userId)` | Return all streaks ordered by start date |
| `getCurrentRecord(userId)` | Return the streak with `isRecord=True` |

#### `src/domain/services/chatsService.py`

| Method | Business rules |
|--------|----------------|
| `getOrCreateChat(senderId, receiverId)` | Check existing active chat · Create if none |
| `sendMessage(senderId, chatId, content)` | Verify sender is a chat participant · Sanitise content · Persist message |
| `getConversation(userId, chatId)` | Verify user is a participant · Return messages with pagination |
| `markConversationAsRead(userId, chatId)` | Call `messageRepository.markAllAsRead()` |
| `getChatList(userId)` | Return all chats the user participates in |

#### `src/domain/services/badgeService.py`

| Method | Business rules |
|--------|----------------|
| `checkAndGrantBadges(userId)` | Called after every streak update · Query current streak and history · Grant applicable badges |
| `getUserBadges(userId)` | Return all `UserBadge` records with `Badge` details |
| `grantBadge(userId, badgeId)` | Check `existsByUserAndBadge` · Grant if not already held |

**Badge milestone rules:**

| Badge | Condition |
|-------|-----------|
| First Day | First streak created |
| One Week | Any streak with duration ≥ 7 days |
| One Month | Any streak with duration ≥ 30 days |
| Three Months | Any streak with duration ≥ 90 days |
| Six Months | Any streak with duration ≥ 180 days |
| One Year | Any streak with duration ≥ 365 days |
| Comeback | Created a new streak after previously resetting |

---

### Phase 3 — Routes

All routes follow the same pattern: validate schema → call service → return response or raise `HTTPException`.

#### `src/api/routes/authRoutes.py`

```
POST /auth/register    → userService.registerUser()
POST /auth/login       → userService.loginUser()     (applies LoginRateLimiter)
POST /auth/refresh     → userService.refreshToken()
POST /auth/logout      → userService.logoutUser()    (requires auth)
```

#### `src/api/routes/userRoutes.py`

```
GET  /users/me         → userService.getProfile()          (requires auth)
PUT  /users/me         → userService.updateProfile()        (requires auth)
PUT  /users/password   → userService.changePassword()       (requires auth)
GET  /users/{userId}   → userService.getPublicProfile()     (requires auth)
```

#### `src/api/routes/streakRoutes.py`

```
GET  /streaks/current  → streakService.getCurrentStreak()   (requires auth)
GET  /streaks/record   → streakService.getCurrentRecord()   (requires auth)
GET  /streaks/history  → streakService.getStreakHistory()   (requires auth)
POST /streaks/end      → streakService.endStreak()          (requires auth)
```

#### `src/api/routes/chatRoutes.py`

```
GET  /chats            → chatsService.getChatList()         (requires auth)
GET  /chats/{chatId}   → chatsService.getConversation()     (requires auth)
POST /chats/send       → chatsService.sendMessage()         (requires auth)
PUT  /chats/{chatId}/read → chatsService.markConversationAsRead() (requires auth)
```

#### `src/api/routes/badgesRoutes.py`

```
GET  /badges           → badgeService.getUserBadges()       (requires auth)
GET  /badges/all       → badgeService.getAllBadges()         (requires auth)
```

---

### Phase 4 — WebSocket

#### `src/websocket/socketManager.py`

```python
# Required setup
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=config.ALLOWED_ORIGINS,
    max_http_buffer_size=102400,   # 100 KB max payload
)

# Events to implement
@sio.event async def connect(sid, environ)       # authenticate JWT, register connection
@sio.event async def disconnect(sid)             # unregister connection
@sio.event async def message(sid, data)          # validate → sanitise → persist → emit to recipient
@sio.event async def typing(sid, data)           # emit typing indicator to recipient
@sio.event async def read(sid, data)             # mark messages as read
```

**Rate limiting for messages:** max 20 messages per minute per user (separate sliding window from HTTP rate limiter).

**Connection limits:** max 5 simultaneous connections per user.

---

### Phase 5 — External Services

#### `src/infrastructure/external/emailService.py`

- Email verification on registration
- Password reset flow
- Recommended library: `fastapi-mail` or `sendgrid`

#### `src/infrastructure/external/storageService.py`

- Profile picture upload
- Recommended: Google Cloud Storage (config keys already present: `STORAGE_SERVICE_URI`, `STORAGE_SERVICE_KEY`)
- Store only the GCS object URL in the database — never raw bytes

---

### Phase 6 — Testing

#### Unit tests (`tests/unit/`)

Test services in isolation by mocking repositories:

```python
def testRegisterUserDuplicateEmail():
    mockRepo = MagicMock()
    mockRepo.findByEmail.return_value = existingUser
    service = UserService(userRepo=mockRepo)
    with pytest.raises(NoHarmException) as exc:
        service.registerUser(request)
    assert exc.value.statusCode == 409

def testStreakAutoResetAfter24h():
    ...
```

#### Integration tests (`tests/integration/`)

Test repositories against a real (test) database:

```python
def testCreateAndFindUser(testDb):
    repo = UserRepository(testDb)
    user = repo.create(...)
    found = repo.findByEmail(user.email)
    assert found.id == user.id
```

#### End-to-end tests (`tests/e2e/`)

Test full HTTP flows via `httpx.AsyncClient`:

```python
async def testLoginFlow(client):
    await client.post("/auth/register", json={...})
    response = await client.post("/auth/login", json={...})
    assert response.status_code == 200
    assert "accessToken" in response.json()
```

---

### Phase 7 — DevOps

- [ ] `Dockerfile` + `docker-compose.yml` (app + PostgreSQL + Redis)
- [ ] GitHub Actions CI: lint → test → build on every PR
- [ ] Nginx config: timeouts, body size limits, rate limiting, SSL termination
- [ ] Sentry integration for error tracking
- [ ] Redis for rate limiter state (multi-worker support)

---

## Dependency Map

```
Route
  └─ depends on → Service
                    └─ depends on → Repository
                                      └─ depends on → Model (SQLAlchemy)
                                                        └─ depends on → Encryption
                                                        └─ depends on → Base (storageService)

Route
  └─ depends on → getCurrentUser (dependency)
                    └─ depends on → JwtHandler
                                      └─ depends on → TokenBlacklist
                                                        └─ depends on → PersistentHashTable
                                                        └─ depends on → Encryption

main.py
  └─ registers → RateLimitMiddleware
                    └─ depends on → IpRateLimiter
  └─ registers → SecurityHeadersMiddleware
  └─ registers → CORSMiddleware
```

---

## Quick Reference — Status Codes

Defined in `.secrets.toml` as `STATUS_CODES`:

| Name | Value | Used in |
|------|-------|---------|
| `disabled` | 0 | User account, streak, badge |
| `enabled` | 1 | User account, streak |
| `deleted` | 2 | Soft delete on all entities |
| `blocked` | 3 | User account |
| `pending` | 4 | Friendship request, chat invite |
| `accepted` | 5 | Friendship |
| `ignored` | 6 | Friendship |
| `unread` | 7 | Message |
| `read` | 8 | Message |
| `banned` | 9 | User account |