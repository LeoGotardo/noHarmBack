# noHarmBack

Backend of the **NoHarm** application — a mobile app for addiction recovery support.

**Stack:** Python · FastAPI · PostgreSQL · WebSocket (Socket.IO) · SQLAlchemy · JWT · Dynaconf

**API Docs:** `https://<domain>/api/docs` (served by the backend behind nginx)

## Contents

- [Frontend](#frontend)
- [Project Structure](#project-structure)
- [Source Code — `src/`](#source-code--src)
  - [`src/api/`](#srcapi)
  - [`src/core/`](#srccore)
  - [`src/domain/`](#srcdomain)
  - [`src/infrastructure/`](#srcinfrastructure)
  - [`src/schemas/`](#srcschemas)
  - [`src/security/`](#srcsecurity)
  - [`src/websocket/`](#srcwebsocket)
  - [`src/main.py`](#srcmainpy)
  - [`src/run.py`](#srcrunpy)
  - [`src/exceptions/`](#srcexceptions)
- [Configuration](#configuration)
  - [Required secrets (`.secrets.toml`)](#required-secrets-secretstoml)
  - [The legal settings, and why they are not constants](#the-legal-settings-and-why-they-are-not-constants)
- [Row Level Security (RLS)](#row-level-security-rls)
- [Pagination](#pagination)
  - [Pagination with RLS](#pagination-with-rls)
- [Getting Started](#getting-started)
- [Deployment (AWS, single container)](#deployment-aws-single-container)
- [Coding Conventions](#coding-conventions)
- [Security](#security)
- [Additional Documentation](#additional-documentation)

---

## Frontend

The sole consumer of this API is [`noHarm`](https://github.com/LeoGotardo/noHarm), a separate sibling
repository — a Vite + React 19 SPA wrapped with Capacitor for iOS/Android. It
consumes the REST API (`VITE_API_URL`) and the Socket.IO server
(`VITE_SOCKET_URL`) documented below, authenticating with the JWT access/refresh
pair issued by `authRoutes.py`.

The two repos **must sit side by side on disk** (`noHarm/` and `noHarmBack/` in
the same parent directory): stage 1 of `docker/Dockerfile` compiles the frontend
bundle, so the build context is that parent, and nginx in the same image serves
the bundle alongside uvicorn. A frontend change therefore ships on a *backend*
deploy — there is no separate frontend pipeline.

| Where to look | What it covers |
|---------------|----------------|
| [`../../noHarm/README.md`](../../noHarm/README.md) | Frontend stack, project layout, env vars, and the Android APK build tutorial |
| [`../../noHarm/CLAUDE.md`](../../noHarm/CLAUDE.md) | Frontend architecture, navigation model, theming, notification IDs, domain rules |
| [`../../noHarm/TESTING.md`](../../noHarm/TESTING.md) | Manual QA checklist for every user-facing flow |
| [`FRONTEND_DESIGN_BRIEF.md`](FRONTEND_DESIGN_BRIEF.md) | API shapes as the frontend consumes them |

Two things this backend owes the frontend:

- **`ALLOWED_ORIGINS` must include `capacitor://localhost` (iOS) and
  `https://localhost` (Android, Capacitor's default scheme since v6; keep
  `http://localhost` too for older builds).** The web build is same-origin with the API and
  never sends a preflight; the Capacitor app is the only cross-origin client.
  Omitting these breaks mobile REST while leaving the socket working — an
  asymmetric failure that is confusing without this note.
- **CSP lives in `docker/security_headers.conf`**, not in the app. Anything the
  frontend loads cross-origin (Google Fonts, Firebase sign-in) has to be listed
  there or it is blocked with no symptom but a console error.

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
│   ├── TESTING.md              # Test suite guide
│   ├── security.md             # Security guide, RLS (§12), business rules (§11)
│   ├── operations.md           # Runbook of the live instance
│   ├── POSTS_PLAN.md           # Design and contract of the Community tab
│   ├── FRONTEND_DESIGN_BRIEF.md
│   └── CLAUDE_DESIGN_PROMPT.md
├── infra/                      # Terraform for an ECS deployment — not provisioned
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
│   │   └── external/           # Firebase app, FCM push, declarative Base
│   ├── schemas/                # Pydantic DTOs
│   ├── security/               # JWT, encryption, rate limiting
│   ├── websocket/              # Socket.IO real-time handlers
│   │   └── handlers/
│   ├── exceptions/             # Custom exceptions
│   ├── jobs/                   # Retention crons and the SSH-access collector
│   ├── main.py                 # FastAPI entry point
│   └── run.py                  # Uvicorn startup script
├── .secrets.toml               # Environment secrets (never commit)
├── alembic.ini
├── migrate.sh                  # alembic upgrade head
├── requirements.txt            # runtime — what the image installs
├── requirements-dev.txt        # + test tooling
└── docker/                     # production image: nginx + uvicorn
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
| `auth.py` | `getCurrentUser` (JWT + account status), `getAdminUser` and `getOfficialUser` (see `core/roles.py`) |
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
| `reportRoutes.py` | Reports: filing one, the reporter's own list, and the admin queue with its review lock |
| `noticeRoutes.py` | Moderation notices: what moderation said to this account, and acknowledging it |
| `postRoutes.py` | The Community tab: feeds, posts, comments, likes, and moderation's remove/restore |
| `notificationRoutes.py` | This device's FCM token and its push categories |
| `adminRoutes.py` | The admin board and, for official accounts, promoting administrators |

Consent, the data export and the two profile sanctions live in `userRoutes.py`
rather than in files of their own, because all six act on the account row:
`GET`/`POST /users/me/consents`, `DELETE /users/me/consents/health`,
`GET /users/me/export`, `PUT /users/{id}/username/reset` and
`PUT /users/{id}/picture/{block|unblock}`.

---

### `src/core/`

Central configuration and resources shared across the entire application.

| File | Description |
|------|-------------|
| `config.py` | Loads and validates environment variables via Dynaconf |
| `database.py` | Creates the SQLAlchemy engine and `SessionLocal` |
| `roles.py` | Who is an administrator (`ADMIN_USER_IDS`, `OFFICIAL_USER_IDS`, `tb_19`) and the public `role` mark |

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
| `consent.py` | Consent | id, userId, document, version, acceptedAt, withdrawnAt |
| `report.py` | Report | id, reporter, reported, reason, details, status, review lock |
| `reportEvidence.py` | ReportEvidence | id, report, kind, sourceId, authorId, content, contentHash |
| `moderationNotice.py` | ModerationNotice | id, userId, kind, reason, message, issuedBy, acknowledgedAt |

#### `src/domain/services/`

Orchestrate business rules. Call `Repositories` to access data and apply rules before returning results to routes.

| File | Responsibility |
|------|----------------|
| `authService.py` | Login, logout, token refresh, Firebase authentication |
| `userService.py` | Profile update, user search, suspensions and the two profile sanctions |
| `streakService.py` | Start, check-in, relapse with record detection. Streaks never expire on their own |
| `friendshipService.py` | Friend request lifecycle, blocking, friend lists |
| `chatService.py` | Chat creation, conversation retrieval |
| `messageService.py` | Message CRUD and read-status transitions |
| `badgeService.py` | Granting and listing achievements |
| `userBadgeService.py` | User-badge association management |
| `auditLogsService.py` | Audit trail operations with pagination |
| `consentService.py` | What the account agreed to and what it still owes: versioned consent to the terms, the privacy policy and — separately — to holding recovery data. Withdrawing the last one deletes the streaks it covered |
| `exportService.py` | Everything this system holds about one account, as one JSON document — the right of access, answered without a support ticket |
| `reportService.py` | Filing a report, the admin queue, the review lock, the abuse ceilings and the evidence capture |
| `noticeService.py` | Warnings, suspension notices and the two profile-sanction notices |
| `postService.py` | The Community tab: visibility, the gates on writing, quotas, moderation |
| `notificationService.py` | Device tokens and push categories |
| `adminService.py` | The admin board's aggregates (cached 60 s) |
| `adminGrantService.py` | Promoting and demoting administrators |
| `errorLogService.py` | The grouped fault log |

---

### `src/infrastructure/`

Concrete implementations of data access and external services.

#### `src/infrastructure/database/models/`

ORM table mappings via SQLAlchemy. Every file defines **only table structure** — no business logic.

Sensitive columns are **encrypted at rest** with AES-GCM (`sqlalchemy_utils`
`StringEncryptedType` + `AesGcmEngine`, key `DATABASE_ENCRYPTION_KEY`). The
columns that are looked up by equality — username, email, device token — also
carry a keyed blind index (HMAC-SHA256 under `BLIND_INDEX_KEY`).

| File | Table | Encrypted fields |
|------|-------|-----------------|
| `userModel.py` | `tb_0` | username, email, profile_picture, birth_date |
| `streakModel.py` | `tb_1` | start_at, end_at, last_checkin |
| `friendshipModel.py` | `tb_2` | — |
| `chatModel.py` | `tb_3` | started_at, ended_at |
| `messageModel.py` | `tb_4` | message, send_at, recived_at |
| `badgeModel.py` | `tb_5` | name, description, icon (milestone stays plain — it is compared) |
| `userBadgesModel.py` | `tb_6` | given_at |
| `auditLogsModel.py` | `tb_7` | description |
| `refreshTokenModel.py` | `tb_8` | — (defined, never written) |
| `notificationModel.py` | `tb_9` | device_fcm |
| `reportModel.py` | `tb_10` | details, reported_username |
| `reportEvidenceModel.py` | `tb_11` | content |
| `moderationNoticeModel.py` | `tb_12` | message, excerpt |
| `consentModel.py` | `tb_13` | — (document, version and both instants are compared) |
| `errorLogModel.py` | `tb_14` | message, traceback |
| `hostAccessModel.py` | `tb_15` | — |
| `postModel.py` / `postCommentModel.py` / `postLikeModel.py` | `tb_16` / `tb_17` / `tb_18` | content / content / — |
| `adminGrantModel.py` | `tb_19` | — |
| `baseModel.py` | — | TimestampMixin (created_at, updated_at) |

#### `src/infrastructure/database/repositories/`

Data access layer. Each file encapsulates queries for a specific model. **Services call Repositories — they never access the database directly.**

| File | Key Methods |
|------|-------------|
| `userRepository.py` | `findById`, `findByEmail`, `findByUsername`, `search`, `findAll`, `create`, `update`, `suspend`, `forceUsernameChange`, `setPictureBlocked`, `softDelete`, `restore`, `purge` |
| `streakRepository.py` | `findById`, `findAllByOwnerId`, `findCurrentStreak`, `findCurrentRecord`, `create`, `updateLastCheckin`, `updateEnd`, `markAsRecord`, `unmarkRecord` |
| `friendshipRepository.py` | `findById`, `findByUsers`, `findAllByUserId`, `findPendingReceived`, `findPendingSent`, `findBlockedUsers`, `setBlocked`, `clearBlock`, `create`, `updateStatus` |
| `chatRepository.py` | `findById`, `findBetween`, `findLatestBetween`, `findAllBySenderId`, `findAllByReciverId`, `create`, `updateStatus`, `updateEndedAt` |
| `messageRepository.py` | `findById`, `findByChatId`, `findUnreadByChatId`, `findRecentByChatId`, `create`, `markAsRead`, `markAllAsRead` |
| `badgeRepository.py` | `findById`, `findAll`, `create`, `update`, `updateStatus`, `softDelete` |
| `userBadgesRepository.py` | `findByUserId`, `findByBadgeId`, `existsByUserAndBadge`, `grant`, `revoke` |
| `auditLogsRepository.py` | `findAll`, `findById`, `findByType`, `findByCatalystId`, `findByDateRange`, `create` |
| `notificationRepository.py` | `add`, `update`, `findActiveByUserId`, `softDelete` |
| `consentRepository.py` | `findByUser`, `findCurrent`, `createMany`, `withdraw` — append-only apart from withdrawal: agreeing again writes a new row, and nothing edits the past |
| `reportRepository.py` / `reportEvidenceRepository.py` | the queue, the review lock, reporter standing; evidence capture and retention |
| `moderationNoticeRepository.py` | `create`, `findByUser`, `acknowledge` |
| `postRepository.py` / `postCommentRepository.py` | feeds and the visibility rule as SQL (`postVisibleTo`), likes, removal and retention |
| `errorLogRepository.py` / `hostAccessRepository.py` | the admin board's Errors and Access tabs |
| `adminGrantRepository.py` | `exists`, `findAll`, `grant`, `revoke` |

There is no repository for `tb_8`: refresh tokens are revoked through the Redis
blacklist only (see `security.md` §7.4).

#### `src/infrastructure/external/`

Integrations with external services.

| File | Description |
|------|-------------|
| `firebaseApp.py` | The one Firebase Admin app per process, used to verify ID tokens |
| `fcmService.py` | Push notifications through FCM, filtered by the device's categories |
| `storageService.py` | Declares `Base` (SQLAlchemy DeclarativeBase) — file uploads planned |

There is no email service: Firebase sends every email the product needs.

---

### `src/schemas/`

DTOs defined with **Pydantic**. Responsible for validating input data and filtering output data from routes, ensuring sensitive information (e.g. `passwordHash`) is never exposed.

| File | Purpose |
|------|---------|
| `authSchemas.py` | `AuthRegisterRequest`, `AuthLoginRequest`, `AuthReactivateRequest`, `AuthRefreshRequest`, `AuthResponse` |
| `userSchemas.py` | `UserCreate`, `UserUpdate`, `ProfileUpdateRequest`, `UserResponse`, `MeResponse`, `UserStatsResponse`, `SuspendRequest`, `SuspensionResponse`, `SanctionRequest`, `SanctionResponse` |
| `streakSchemas.py` | `StreakResponse`, `StreakListResponse`, `StreakStartRequest`, `StreakEndRequest` |
| `friendshipSchemas.py` | `FriendshipCreate`, `FriendshipResponse`, `FriendshipListResponse`, `FriendUserInfo` |
| `chatSchemas.py` | `ChatCreate`, `ChatResponse`, `ChatListResponse` |
| `messageSchemas.py` | `MessageCreate`, `MessageResponse`, `MessageListResponse` |
| `badgeSchemas.py` | `BadgeCreate`, `BadgeUpdate`, `BadgeResponse`, `BadgeListResponse` |
| `userBadgeSchemas.py` | `UserBadgeResponse`, `UserBadgeCreate`, `UserBadgeUpdate`, `UserBadgeListResponse` |
| `auditLogsSchemas.py` | `AuditLogsResponse`, `AuditLogsCreate`, `AuditLogsListResponse` |
| `consentSchemas.py` | `ConsentAcceptRequest`, `ConsentRecord`, `ConsentStatusResponse`, `ConsentWithdrawResponse` |
| `reportSchemas.py` / `noticeSchemas.py` / `postSchemas.py` / `adminSchemas.py` | see the root `CLAUDE.md`, Schemas |
| `paginationSchemas.py` | `PaginationParams`, `PaginatedResponse[T]` |

---

### `src/security/`

Reusable security modules shared across the application.

| File | Description |
|------|-------------|
| `jwtHandler.py` | Generation and validation of Access and Refresh tokens with blacklist support |
| `tokenBlacklist.py` | JWT revocation list in Redis (`SETEX` with the token's remaining lifetime) |
| `persistentHashTable.py` | The older append-only JSONL store — imported by nothing |
| `rateLimiter.py` | Redis-backed: per-IP sliding window (global middleware), login lockout per UID, and the per-account report and content quotas |
| `limiter.py` | Shared `slowapi` `Limiter` instance — imported by every route file for per-route `@limiter.limit(...)` decorators |
| `middleware.py` | `RateLimitMiddleware` and `SecurityHeadersMiddleware` registered globally in `main.py` |
| `sanitizer.py` | HTML sanitisation via `bleach` for XSS prevention |
| `encryption.py` | Keyed blind index (`hash`, HMAC-SHA256), unkeyed `digest`, Argon2 helpers and Fernet helpers no column uses — column encryption is AES-GCM in the models |

**JWT flow:**
- Access token: 15-minute lifetime, signed with `JWT_SECRET_KEY`
- Refresh token: 7-day lifetime, signed with `JWT_REFRESH_SECRET_KEY`. Not stored — `tb_8` exists but is never written
- Each token carries a unique `jti` claim that enables individual revocation
- Refresh token rotation: old token is blacklisted on every `/auth/refresh` call before new tokens are issued
- Revoked JTIs are stored hashed (SHA-256) in Redis, expiring with the token

**Token blacklist:**
The blacklist lives in Redis: each revoked JTI is stored as `jti:<sha256>` with a
TTL equal to the token's remaining lifetime, so expired entries remove
themselves and a logout is honoured by every instance.

**Rate limiting — two layers:**

| Layer | Implementation | Scope |
|-------|---------------|-------|
| Global floor | `RateLimitMiddleware` (`rateLimiter.py`) | 240 req/min per IP (`RATE_LIMIT_MAX_REQUESTS`); a breach blocks for 60 s, doubling on repeat up to 900 s |
| Per-route ceiling | `slowapi` decorator (`limiter.py`) | Stricter per endpoint (e.g. 5/min on register, 10/min on login) |

Both layers key on `security/clientIp.py` and keep their counters in Redis, so
they survive a restart and are shared across instances; `limiter.py` falls back
to in-memory counting if Redis is down at boot.

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

Application entry point. Initialises FastAPI, registers middlewares (CORS, rate limiting, security headers), wires up the `slowapi` limiter state and `RateLimitExceeded` handler, includes all route routers, and mounts the Socket.IO server alongside HTTP.

### `src/run.py`

Convenience script to start the server with Uvicorn using settings from `config`.

### `src/exceptions/`

| File | Description |
|------|-------------|
| `baseExceptions.py` | `NoHarmException` — base class with `statusCode`, `errorCode`, `message`, `details`, and `toDict()` |
| `databaseExceptions.py` | `NoEngineException`, `NoSessionException`, `NoDatabaseParameterException` |

---

## Configuration

The application uses [Dynaconf](https://www.dynaconf.com/) with `.secrets.toml`,
whose sections are `[default]`, `[dev]`, `[alembic]` and `[prod]`. `APP_ENV`
picks one, and **it defaults to `prod`** — an unset or misspelled value silently
targets production:

```bash
export APP_ENV=dev   # or alembic, prod
```

In the container the values arrive as environment variables instead
(`docker/prod.env`); `.secrets.toml` never enters the image.

### Required secrets (`.secrets.toml`)

```toml
[dev]
ENCRYPTION_KEY          = "..."
DATABASE_ENCRYPTION_KEY = "..."   # AES-GCM key for the encrypted columns
BLIND_INDEX_KEY         = "..."   # HMAC key for the blind indexes — must differ from the one above
REDIS_URL               = "redis://localhost:6379/0"
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
ALLOWED_ORIGINS         = ["*"]
DEBUG                   = true
PORT                    = 8080
STATUS_CODES            = { disabled = 0, enabled = 1, deleted = 2, blocked = 3, pending = 4, accepted = 5, ignored = 6, unread = 7, read = 8, banned = 9 }
```

### The legal settings, and why they are not constants

All optional, all with defaults, and all of them change what the app does the
moment they change:

```toml
TERMS_VERSION           = "1.0"   # bump → every account is asked again
PRIVACY_VERSION         = "1.0"
HEALTH_CONSENT_VERSION  = "1.0"   # separate on purpose; never fold it into the terms
MINIMUM_AGE_YEARS       = 18
```

Publishing a new revision of a document is **only** a version bump here: every
stored consent goes stale by comparison and the app shows the gate instead of
itself until the account accepts. That is the whole mechanism, and it is why a
consent row stores a version rather than a boolean — a boolean would mean an
account had agreed, once, to a text that has since been rewritten.

`MINIMUM_AGE_YEARS` is enforced in `AuthService._requireMinimumAge` against a
self-declared date of birth. No identity provider this app uses carries an age
claim, so what it buys is the record that the question was asked and answered,
not proof.

The front end mirrors two of these for copy only — `VITE_MINIMUM_AGE` and
`VITE_DELETION_GRACE_DAYS`. Every `VITE_*` is inlined at build time, so both
have to be passed as build args (`docker/Dockerfile`, `deploy-host.sh`,
`.github/workflows/deploy.yml`) or they compile to `undefined` and the screen
quietly states a different number from the one the backend enforces.

Generate secure secrets with:
```python
import secrets
print(secrets.token_urlsafe(32))  # run three times for the three keys
```

---

## Row Level Security (RLS)

PostgreSQL RLS policies (migration `20260831_02` and the migrations that added
each later table) are a floor under the service layer's own checks. The table
of rules is in the root [`CLAUDE.md`](../CLAUDE.md), Row Level Security, and the
reasoning, setup and troubleshooting in [`security.md`](security.md) §12. Two
things to know before reading either:

- `tb_0` (users) is readable across accounts — search, public profiles and
  every enriched response need it. Only UPDATE/DELETE are owner-scoped.
- With no context set, every policy passes. `getDbWithRLS` is what turns RLS on
  for a request; admin routes and jobs use `getDb` on purpose.

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

### Pagination with RLS

When using `getDbWithRLS`, `total` reflects the RLS-filtered count, not the
full table — see `security.md` §10, "Pagination with RLS", for the effect per
table.

---

## Getting Started

```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux / macOS
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements-dev.txt   # runtime + pytest & co.; the image installs requirements.txt only

# Configure secrets: create .secrets.toml with a [dev] section (see
# Configuration above). There is no template file in the repo; for the
# container path, docker/prod.env.example lists every variable.

# Run database migrations — mandatory, not optional: nothing else creates the
# schema at startup, and a database without them has no RLS policies.
APP_ENV=alembic alembic upgrade head

# Start the server
cd src && python run.py
# or
uvicorn src.main:app --reload
```

---

## Deployment (AWS, single container)

**What is live today**: a single EC2 t3.micro (`noharm.site`, `34.225.81.236`)
running `docker/compose.host.yaml` — the application alongside Postgres and
Redis in containers, with nginx terminating TLS using a Let's Encrypt
certificate (`TLS_MODE=container`). The deploy is `docker/deploy-host.sh`, which
builds the image on the developer's machine and ships it over SSH: `vite build`
needs more RAM than the instance has. The runbook — addresses, the two cron
jobs, migrations, restore and the accepted risks — is in
[`operations.md`](operations.md).

The Terraform in `infra/` (ALB + Fargate + RDS + ElastiCache) describes a
**different, unprovisioned** deployment, kept for when one instance stops being
enough. `terraform apply` today would create a second parallel environment, and
bill for it.

Front end and back end live in the same image. nginx terminates TLS, serves the
Vite bundle and forwards `/api` (without the prefix) and `/ws` to uvicorn on
`127.0.0.1:8080` — which listens nowhere else, and that is what stops anyone
from forging `X-Forwarded-For`.

Where TLS terminates is chosen by `TLS_MODE`:

- `alb` (default, ECS) — the ALB terminates TLS with an ACM certificate and the
  container serves plain `:80`. Requires `TRUSTED_PROXY_CIDRS` (the VPC range):
  that is what lets nginx recover the real client IP from `X-Forwarded-For`.
  Without it the whole world falls into the same rate-limit bucket.
- `container` (compose.prod.yaml) — nginx terminates TLS and the certificate
  pair in `/etc/nginx/certs` is a hard dependency.

Config lives in `docker/`; the details are in the root `CLAUDE.md`, Deployment
section. The step-by-step for the first deploy of the ECS stack — for the day it
gets used — is in `infra/README.md`.

Things that commonly bite:

- The build context is the **parent directory of both repos** — `noHarm/` and
  `noHarmBack/` must sit side by side, because stage 1 compiles the bundle. The
  deploy workflow does two checkouts for that reason.
- The entrypoint refuses to start with `FIREBASE_AUTH_EMULATOR_HOST` set,
  without the certificates in `container` mode, and without
  `TRUSTED_PROXY_CIDRS` in `alb` mode.
- Migrations do not run on their own: `RUN_MIGRATIONS=true` on **one** instance,
  or — what ECS does — as a dedicated task (`<image> migrate`, which runs the
  upgrade and exits). N containers starting together would race for the same
  upgrade. On the current instance this is a manual
  `docker compose run --rm app migrate`.
- The application connects as `noharm_app` (`NOSUPERUSER`, `NOBYPASSRLS`),
  created by `docker/postgres-init/10-app-role.sh` when the volume is
  initialized. That is what RLS depends on to be worth anything: `POSTGRES_USER`
  is a superuser and would silently ignore every policy.

On the ECS path, Postgres and Redis are external (RDS / ElastiCache). Alembic
uses the unpooled URL because pgBouncer is incompatible with DDL operations.
Both URLs can be left blank: the entrypoint builds them from `DATABASE_HOST` /
`NAME` / `USER` / `PASSWORD`, which is what lets RDS be the sole owner of the
password.

---

## Coding Conventions

The project uses **camelCase** for all Python variables, functions, and attributes:

```python
# ✅ Project standard
def getUserById(userId: str): ...
passwordHash = encryption.encryptPass(...)
createdAt = datetime.now(timezone.utc)

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
| `docs/TESTING.md` | Test suite guide — patterns, layout, how to run the integration suite |
| `docs/security.md` | Security guide, audit checklist, RLS, pagination, and business rules |
| `docs/operations.md` | Runbook of the live EC2 instance — access, cron jobs, deploy, migrations, backup/restore, accepted risks |
| `infra/README.md` | Terraform stack (ECS/RDS/ElastiCache) — **not provisioned** |
| [`../../noHarm/README.md`](../../noHarm/README.md) | Frontend repo — stack, layout, and the Android APK build tutorial |
