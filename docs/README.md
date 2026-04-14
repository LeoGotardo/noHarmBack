# noHarmBack

Backend of the **NoHarm** application — a mobile app for addiction recovery support.

**Stack:** Python · FastAPI · PostgreSQL · WebSocket (Socket.IO) · SQLAlchemy · JWT · Dynaconf

---

## Project Structure

```
noHarmBack/
├── alembic/                    # Database migrations
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── docs/
│   ├── README.md               # This file
│   ├── TODO.md                 # Implementation status
│   ├── security.md             # Security guide
│   ├── RLS_SETUP.md           # Row Level Security documentation
│   ├── PAGINATION_GUIDE.md    # Pagination system documentation
│   └── requirements.txt        # Python dependencies
├── src/
│   ├── api/
│   │   ├── dependencies/       # FastAPI dependencies (auth, database)
│   │   └── routes/             # HTTP endpoints
│   ├── core/                   # Configuration, database engine
│   ├── domain/
│   │   ├── entities/           # Pure domain objects
│   │   └── services/           # Business logic
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── models/         # SQLAlchemy ORM models
│   │   │   └── repositories/   # Data access layer
│   │   └── external/           # External services (email, storage)
│   ├── schemas/                # Pydantic DTOs
│   ├── security/               # JWT, encryption, rate limiting
│   ├── websocket/              # Socket.IO real-time handlers
│   │   └── handlers/
│   ├── exceptions/             # Custom exceptions
│   ├── main.py                 # FastAPI entry point
│   └── run.py                  # Uvicorn startup script
├── .secrets.toml               # Environment secrets (never commit)
├── alembic.ini
├── migrate.sh                  # Vercel migration script
├── requirements.txt
└── vercel.json
```

---

## Source Code — `src/`

The application is organised in layers following **Clean Architecture**. Each layer has a single responsibility and depends only on layers below it.

```
HTTP Request
    │
    ▼
Route        — validates schema (Pydantic) · extracts JWT (Dependency)
    │
    ▼
Service      — applies business rules · orchestrates repositories
    │
    ▼
Repository   — executes database queries
    │
    ▼
Model        — ORM maps table ↔ Python object
    │
    ▼
PostgreSQL
```

---

### `src/api/`

Presentation layer. Exposes the application to the outside world over HTTP.

#### `src/api/dependencies/`

Reusable FastAPI dependencies injected into routes.

| File | Description |
|------|-------------|
| `auth.py` | Extracts and validates the authenticated user from the JWT (`getCurrentUser`) |
| `database.py` | Provides database sessions: `getDb` (no RLS) and `getDbWithRLS` (with Row Level Security) |

#### `src/api/routes/`

HTTP endpoints. Each file groups routes for one domain. Routes contain **no business logic** — they receive the request, delegate to the corresponding `Service`, and return the response.

| File | Description |
|------|-------------|
| `authRoutes.py` | Authentication: login, logout, token refresh, registration |
| `userRoutes.py` | User profile: registration, profile, data update |
| `streakRoutes.py` | Streaks: query, increment, and reset clean days |
| `friendshipRoutes.py` | Friendships: send/accept/reject/block friend requests |
| `chatRoutes.py` | Chats: conversation creation and history |
| `messageRoutes.py` | Messages: per-message CRUD and read status |
| `badgesRoutes.py` | Badges: global badge list |
| `userBadgesRoutes.py` | User badges: per-user badge records |
| `auditLogsRoutes.py` | Audit logs: audit trail query with pagination |

---

### `src/core/`

Central configuration and resources shared across the entire application.

| File | Description |
|------|-------------|
| `config.py` | Loads and validates environment variables via Dynaconf |
| `database.py` | Creates the SQLAlchemy engine and `SessionLocal` |

---

### `src/domain/`

Application core. Contains business rules completely isolated from infrastructure details (database, HTTP, etc.).

#### `src/domain/entities/`

Pure domain concept representations, with no ORM or framework coupling.

| File | Entity | Key Fields |
|------|--------|------------|
| `user.py` | User | id, username, email, profilePicture, status, timestamps |
| `streak.py` | Streak | id, ownerId, start, end, status, isRecord |
| `friendship.py` | Friendship | id, sender, receiver, sendAt, receivedAt, status |
| `chat.py` | Chat | id, sender, receiver, startedAt, endedAt, status, messages |
| `message.py` | Message | id, chat, sender, message, status, sendAt, receivedAt |
| `badge.py` | Badge | id, name, description, milestone, icon, status |
| `userBadge.py` | UserBadge | id, userId, badgeId, givenAt, status |
| `auditLogs.py` | AuditLogs | id, type, catalystId, catalyst, description, timestamps |

#### `src/domain/services/`

Orchestrate business rules. Call `Repositories` to access data and apply rules before returning results to routes.

| File | Responsibility |
|------|----------------|
| `authService.py` | Login, logout, token refresh, Firebase authentication |
| `userService.py` | Registration, profile update, user search, password changes |
| `streakService.py` | Daily increment, expiry check, reset with history |
| `friendshipService.py` | Friend request lifecycle, blocking, friend lists |
| `chatService.py` | Chat creation, conversation retrieval |
| `messageService.py` | Message CRUD and read-status transitions |
| `badgeService.py` | Granting and listing achievements |
| `userBadgeService.py` | User-badge association management |
| `auditLogsService.py` | Audit trail operations with pagination |

---

### `src/infrastructure/`

Concrete implementations of data access and external services.

#### `src/infrastructure/database/models/`

ORM table mappings via SQLAlchemy. Every file defines **only table structure** — no business logic.

All sensitive fields (username, email, message content, timestamps, etc.) are stored **encrypted at rest** using AES-256 (Fernet) and are also indexed by a SHA-256 hash to allow equality queries without exposing plaintext.

| File | Table | Encrypted Fields |
|------|-------|-----------------|
| `userModel.py` | `tb_0` | username, email, profilePicture |
| `streakModel.py` | `tb_1` | start, end |
| `friendshipModel.py` | `tb_2` | sendAt, receivedAt |
| `chatModel.py` | `tb_3` | startedAt, endedAt |
| `messageModel.py` | `tb_4` | message, sendAt, receivedAt |
| `badgeModel.py` | `tb_5` | name, description, milestone, icon |
| `userBedgesModel.py` | `tb_6` | givenAt |
| `auditLogsModel.py` | `tb_7` | description |
| `refreshTokenModel.py` | `tb_8` | tokenHash |
| `baseModel.py` | — | TimestampMixin (createdAt, updatedAt) |

#### `src/infrastructure/database/repositories/`

Data access layer. Each file encapsulates queries for a specific model. **Services call Repositories — they never access the database directly.**

| File | Key Methods |
|------|-------------|
| `userRepository.py` | `findById`, `findByEmail`, `findByUsername`, `findAll`, `create`, `update`, `updateStatus`, `softDelete` |
| `streakRepository.py` | `findById`, `findByOwnerId`, `findAllByOwnerId`, `findCurrentStreak`, `findCurrentRecord`, `create`, `update`, `markAsRecord`, `updateStatus` |
| `friendshipRepository.py` | `findById`, `findByPair`, `findAllByReceiverPending`, `findAllBySenderId`, `create`, `updateStatus` |
| `chatRepository.py` | `findById`, `findByParticipants`, `findAllByUserId`, `create`, `updateStatus`, `updateEndedAt` |
| `messageRepository.py` | `findById`, `findByChatId`, `findUnreadByChatId`, `create`, `markAsRead`, `markAllAsRead`, `updateStatus` |
| `badgeRepository.py` | `findById`, `findAll`, `create`, `update`, `updateStatus`, `softDelete` |
| `userBadgesRepository.py` | `findByUserId`, `findByBadgeId`, `existsByUserAndBadge`, `grant`, `revoke`, `listAll` |
| `auditLogsRepository.py` | `findById`, `findByType`, `findByCatalystId`, `findByDateRange`, `findAllPaginated`, `create` |
| `refreshTokenRepository.py` | `findByTokenHash`, `create`, `deleteByUserId`, `deleteExpired` |

#### `src/infrastructure/external/`

Integrations with external services.

| File | Description |
|------|-------------|
| `emailService.py` | Email sending (verification, password recovery) — **empty** |
| `storageService.py` | Declares `Base` (SQLAlchemy DeclarativeBase) — file uploads planned |

---

### `src/schemas/`

DTOs defined with **Pydantic**. Responsible for validating input data and filtering output data from routes, ensuring sensitive information (e.g. `passwordHash`) is never exposed.

| File | Purpose |
|------|---------|
| `authSchemas.py` | `AuthRegisterRequest`, `AuthLoginRequest`, `TokenResponse` |
| `userSchemas.py` | `UserRegisterRequest`, `UserPrivateResponse`, `UserPublicResponse`, `UserUpdateRequest` |
| `streakSchemas.py` | `StreakResponse`, `StreakResetRequest` |
| `friendshipSchemas.py` | `FriendshipRequest`, `FriendshipResponse`, `FriendshipListResponse` |
| `chatSchemas.py` | `ChatResponse`, `ConversationResponse` |
| `messageSchemas.py` | `MessageRequest`, `MessageResponse`, `MessageListResponse` |
| `badgeSchemas.py` | `BadgeResponse`, `BadgeListResponse` |
| `userBadgeSchemas.py` | `UserBadgeResponse`, `UserBadgeCreate`, `UserBadgeUpdate`, `UserBadgeListResponse` |
| `auditLogsSchemas.py` | `AuditLogsResponse`, `AuditLogsCreate`, `AuditLogsListResponse` |
| `paginationSchemas.py` | `PaginationParams`, `PaginatedResponse[T]` |

---

### `src/security/`

Reusable security modules shared across the application.

| File | Description |
|------|-------------|
| `jwtHandler.py` | Generation and validation of Access and Refresh tokens with blacklist support |
| `tokenBlacklist.py` | Persistent JWT revocation list (append-only JSONL log + in-memory hashtable) |
| `persistentHashTable.py` | Append-only log data structure with O(1) write and periodic compaction |
| `rateLimiter.py` | IP-based rate limiting (sliding window) + login brute-force protection per username |
| `middleware.py` | `RateLimitMiddleware` and `SecurityHeadersMiddleware` registered globally in `main.py` |
| `sanitizer.py` | HTML sanitisation via `bleach` for XSS prevention |
| `encryption.py` | AES-256 symmetric encryption (Fernet) + Argon2 password hashing + SHA-256 hashing |

**JWT flow:**
- Access token: 15-minute lifetime, signed with `JWT_SECRET_KEY`
- Refresh token: 7-day lifetime, signed with `JWT_REFRESH_SECRET_KEY`, stored hashed in database
- Each token carries a unique `jti` claim that enables individual revocation
- Revoked JTIs are stored hashed (SHA-256) in a persistent JSONL blacklist

**Token blacklist:**
The blacklist uses `PersistentHashTable` — an append-only JSONL file that survives server restarts. On startup, state is rebuilt by replaying log events. Expired entries are removed via `cleanup()`. JTIs are stored as SHA-256 hashes — plaintext JTIs are never written to disk.

---

### `src/websocket/`

Real-time communication via Socket.IO.

| File | Description |
|------|-------------|
| `socketManager.py` | Manages WebSocket connections: JWT auth at connection time, message rate limiting, payload validation, event routing |

#### `src/websocket/handlers/`

Handlers isolated by responsibility, called by `socketManager`.

| File | Description |
|------|-------------|
| `chatHandlers.py` | Real-time chat message processing |
| `presenceHandlers.py` | User online/offline status, typing indicators |

**WebSocket Features:**
- **JWT Authentication**: Mandatory token validation on every `connect` event
- **Rate Limiting**: Message throttling (configurable per-user limits)
- **Connection Limits**: Maximum simultaneous connections per user
- **Rooms**: User-specific rooms (`user_{userId}`) and chat rooms (`chat_{chatId}`)

---

### `src/main.py`

Application entry point. Initialises FastAPI, registers middlewares (CORS, rate limiting, security headers), includes routes, and mounts the Socket.IO server alongside HTTP.

### `src/run.py`

Convenience script to start the server with Uvicorn using settings from `config`.

### `src/exceptions/`

| File | Description |
|------|-------------|
| `baseExceptions.py` | `NoHarmException` — base class with `statusCode`, `errorCode`, `message`, `details`, and `toDict()` |
| `databaseExceptions.py` | `NoEngineException`, `NoSessionException`, `NoDatabaseParameterException` |

---

## Configuration

The application uses [Dynaconf](https://www.dynaconf.com/) with `.secrets.toml` and supports three environments: `development`, `staging`, and `production`.

Set the active environment with the `ENV` environment variable:
```bash
export ENV=development   # or staging, production
```

### Required secrets (`.secrets.toml`)

```toml
[development]
ENCRYPTION_KEY          = "..."   # Master key for AES-256 field encryption
DATABASE_URL            = "postgres://..."
DATABASE_URL_UNPOOLED   = "postgresql://..."
DATABASE_HOST           = "..."
DATABASE_NAME           = "..."
DATABASE_USER           = "..."
DATABASE_PASSWORD       = "..."
JWT_SECRET_KEY          = "..."   # Access token signing key
JWT_REFRESH_SECRET_KEY  = "..."   # Refresh token signing key
JWT_ALGORITHM           = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES  = 15
REFRESH_TOKEN_EXPIRE_DAYS    = 7
STORAGE_PATH            = "data"
ALLOWED_ORIGINS         = ["*"]
DEBUG                   = true
PORT                    = 8080
STATUS_CODES            = { disabled = 0, enabled = 1, deleted = 2, blocked = 3, pending = 4, accepted = 5, ignored = 6, unread = 7, read = 8, banned = 9 }
```

Generate secure secrets with:
```python
import secrets
print(secrets.token_urlsafe(32))  # run three times for the three keys
```

---

## Row Level Security (RLS)

PostgreSQL RLS policies enforce data access control at the database level:

| Table | Code | Policy | Access Rule |
|-------|------|--------|-------------|
| users | `tb_0` | users_own_data | Can only see own row |
| streaks | `tb_1` | streaks_own_data | Can only see own streaks |
| friendships | `tb_2` | friendships_participant_data | Can see if sender OR receiver |
| chats | `tb_3` | chats_participant_data | Can see if sender OR receiver |
| messages | `tb_4` | messages_sender_data | Can see messages they sent |
| badges | `tb_5` | badges_read_all | Global read-only table |
| user_badges | `tb_6` | user_badges_own_data | Can only see own badges |
| audit_logs | `tb_7` | audit_logs_own_data | Can only see own audit logs |

Use `getDbWithRLS` in routes to automatically filter queries to the authenticated user's data. See `docs/RLS_SETUP.md` for full details.

---

## Pagination

Generic pagination for list endpoints.

**Defaults**: `page=1`, `pageSize=20` (max 100)

**Usage in routes:**
```python
from schemas.paginationSchemas import PaginationParams, PaginatedResponse

@router.get("/items", response_model=PaginatedResponse[ItemResponse])
def getItems(
    db: Session = Depends(getDbWithRLS),
    pagination: PaginationParams = Depends(),
):
    return service.getAllPaginated(pagination)
```

**Response format:**
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "pageSize": 20,
  "totalPages": 5,
  "hasNext": true,
  "hasPrevious": false
}
```

**Files:**
- `schemas/paginationSchemas.py` — `PaginationParams`, `PaginatedResponse[T]`
- `infrastructure/database/paginationUtils.py` — `paginateQuery()`, `PaginatedRepository` mixin

---

## Getting Started

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Configure secrets
cp .env.example .secrets.toml
# Edit .secrets.toml with your values

# Run database migrations
ENV=development alembic upgrade head

# Start the server
cd src && python run.py
# or
uvicorn src.main:app --reload
```

---

## Deployment (Vercel)

The project is configured for Vercel serverless deployment via `vercel.json`. Migrations are run automatically on build via `migrate.sh` (triggered by `package.json`'s `vercel-build` script).

The database is hosted on **Neon** (serverless PostgreSQL). Alembic uses the unpooled connection URL because pgBouncer (pooled) is incompatible with Alembic's DDL operations.

---

## Coding Conventions

The project uses **camelCase** for all Python variables, functions, and attributes:

```python
# ✅ Project standard
def getUserById(userId: str): ...
passwordHash = encryption.encryptPass(...)
createdAt = datetime.utcnow()

# ❌ Not used (PEP 8 default)
def get_user_by_id(user_id: str): ...
```

Class names and file names follow PascalCase and camelCase respectively, consistent with the rest of the codebase.

---

## Security

See `docs/security.md` for the complete security guide covering:
- Authentication attacks (JWT theft, brute force)
- Injection attacks (SQL injection, XSS, mass assignment)
- Session attacks (CSRF, CORS)
- Denial of Service protections
- Data attacks (encryption, IDOR prevention)
- WebSocket security
- Account & identity attacks
- Infrastructure risks
- Supply chain security

---

## Additional Documentation

| Document | Description |
|----------|-------------|
| `docs/TODO.md` | Current implementation status |
| `docs/security.md` | Security guide and audit checklist |
| `docs/RLS_SETUP.md` | Row Level Security setup and usage |
| `docs/PAGINATION_GUIDE.md` | Pagination system documentation |
| `docs/rules.md` | Project rules and conventions |
| `docs/UNIMPLEMENTABLE_RULES.md` | Rules that cannot be implemented |
