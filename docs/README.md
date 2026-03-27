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
│   ├── TODO.md                 # Architecture context and implementation plan
│   ├── security.md             # Security guide — covered attacks and countermeasures
│   └── requirements.txt        # Python dependencies
├── src/
│   ├── api/
│   │   ├── dependencies/
│   │   └── routes/
│   ├── core/
│   ├── domain/
│   │   ├── entities/
│   │   └── services/
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── models/
│   │   │   └── repositories/
│   │   └── external/
│   ├── schemas/
│   ├── security/
│   ├── websocket/
│   │   └── handlers/
│   ├── main.py
│   └── run.py
├── .secrets.toml               # Environment secrets (never commit)
├── alembic.ini
├── migrate.sh
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
| `database.py` | Provides the database session (`getDb`) to routes |

#### `src/api/routes/`

HTTP endpoints. Each file groups routes for one domain. Routes contain **no business logic** — they receive the request, delegate to the corresponding `Service`, and return the response.

| File | Description |
|------|-------------|
| `authRoutes.py` | Authentication routes: login, logout, token refresh |
| `userRoutes.py` | User routes: registration, profile, data update |
| `streakRoutes.py` | Streak routes: query, increment, and reset clean days |
| `chatRoutes.py` | Message routes: conversation history |
| `badgesRoutes.py` | Achievement routes: list and query user badges |

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
| `chat.py` | Chat | id, sender, reciver, startedAt, endedAt, status, messages |
| `message.py` | Message | id, chat, sender, message, status, sendAt, recivedAt |
| `badge.py` | Badge | id, name, description, milestone, icon, status |
| `userBadge.py` | UserBadge | id, userId, badgeId, givenAt, status |
| `friendship.py` | Friendship | id, sender, reciver, sendAt, recivedAt, status |
| `auditLogs.py` | AuditLogs | id, type, catalistId, catalist, description, timestamps |

#### `src/domain/services/`

Orchestrate business rules. Call `Repositories` to access data and apply rules before returning results to routes.

| File | Responsibility |
|------|----------------|
| `userService.py` | Registration, profile update, user search |
| `streakService.py` | Daily increment, expiry check, reset with history |
| `chatsService.py` | Sending and retrieving messages, recipient validation |
| `badgeService.py` | Granting and listing achievements |

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
| `friendshipModel.py` | `tb_2` | sendAt, recivedAt |
| `chatModel.py` | `tb_3` | startedAt, endedAt |
| `messageModel.py` | `tb_4` | message, sendAt, recivedAt |
| `badgeModel.py` | `tb_5` | name, description, milestone, icon |
| `userBedgesModel.py` | `tb_6` | givenAt |
| `auditLogsModel.py` | `tb_7` | description |
| `baseModel.py` | — | TimestampMixin (createdAt, updatedAt) |

#### `src/infrastructure/database/repositories/`

Data access layer. Each file encapsulates queries for a specific model. **Services call Repositories — they never access the database directly.**

| File | Key Methods |
|------|-------------|
| `userRepository.py` | `findById`, `findByEmail`, `findByUsername`, `findAll`, `create`, `update`, `updateStatus`, `softDelete` |
| `streakRepository.py` | `findById`, `findByOwnerId`, `findAllByOwnerId`, `findCurrentStreak`, `findCurrentRecord`, `create`, `update`, `markAsRecord`, `updateStatus` |
| `chatRepository.py` | `findById`, `findByParticipants`, `findAllByUserId`, `create`, `updateStatus`, `updateEndedAt` |
| `messageRepository.py` | `findById`, `findByChatId`, `findUnreadByChatId`, `create`, `markAsRead`, `markAllAsRead`, `updateStatus` |
| `friendshipRepository.py` | `findById`, `findByPair`, `findAllByReciverPending`, `findAllBySenderId`, `create`, `updateStatus` |
| `badgeRepository.py` | `findById`, `findAll`, `create`, `update`, `updateStatus`, `softDelete` |
| `userBadgesRepository.py` | `findByUserId`, `findByBadgeId`, `existsByUserAndBadge`, `grant`, `revoke`, `listAll` |
| `auditLogsRepository.py` | `findById`, `findByType`, `findByCatalystId`, `findByDateRange`, `create` |

#### `src/infrastructure/external/`

Integrations with external services.

| File | Description |
|------|-------------|
| `emailService.py` | Email sending (verification, password recovery) |
| `storageService.py` | Declares `Base` (SQLAlchemy DeclarativeBase) — file/photo uploads planned |

---

### `src/schemas/`

DTOs defined with **Pydantic**. Responsible for validating input data and filtering output data from routes, ensuring sensitive information (e.g. `passwordHash`) is never exposed.

| File | Purpose |
|------|---------|
| `userSchemas.py` | `UserRegisterRequest`, `UserResponse`, `UserUpdateRequest` |
| `streakSchemas.py` | `StreakResponse`, `StreakResetRequest` |
| `chatSchemas.py` | `MessageRequest`, `MessageResponse`, `ConversationResponse` |
| `badgeSchemas.py` | `BadgeResponse`, `BadgeListResponse` |

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
- Refresh token: 7-day lifetime, signed with `JWT_REFRESH_SECRET_KEY`
- Each token carries a unique `jti` claim that enables individual revocation
- Revoked JTIs are stored hashed (SHA-256) in a persistent JSONL blacklist

**Token blacklist:**
The blacklist uses `PersistentHashTable` — an append-only JSONL file that survives server restarts. On startup, state is rebuilt by replaying log events. Expired entries are removed via `cleanup()`.

---

### `src/websocket/`

Real-time communication via Socket.IO.

| File | Description |
|------|-------------|
| `socketManager.py` | Manages WebSocket connections: JWT auth, message rate limiting, payload validation, event routing |

#### `src/websocket/handlers/`

Handlers isolated by responsibility, called by `socketManager`.

| File | Description |
|------|-------------|
| `chatHandlers.py` | Real-time chat message processing |
| `presenceHandlers.py` | User online/offline status |

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
```

Generate secure secrets with:
```python
import secrets
print(secrets.token_urlsafe(32))  # run three times for the three keys
```

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