# NoHarm Backend — Implementation Status

This document tracks the current state of the backend architecture and components.

---

## Current State

### What is Done ✅

| Layer                      | Component                                                             | Status      |
| -------------------------- | --------------------------------------------------------------------- | ----------- |
| **Project Structure**      | Clean Architecture (4 layers)                                         | ✅ Complete |
| **Configuration**          | Dynaconf multi-environment                                            | ✅ Complete |
| **Database**               | SQLAlchemy engine + session                                           | ✅ Complete |
| **Migrations**             | Alembic setup                                                         | ✅ Complete |
| **Deployment**             | Single container: nginx + uvicorn (`docker/`), TLS via ALB or its own | ✅ Complete |
| **Deployment (live)**      | EC2 t3.micro, `compose.host.yaml`, `deploy-host.sh` (`docs/operations.md`) | ✅ Complete |
| **Non-bypassing app role** | `noharm_app` NOSUPERUSER/NOBYPASSRLS via `postgres-init/10-app-role.sh` | ✅ Complete |
| **Infra as code**          | Terraform: VPC, RDS, ElastiCache, ECR, ALB, ECS, Secrets (`infra/`)   | ⚠️ Written, **not provisioned** |
| **CI/CD**                  | `deploy.yml`: build 2 repos → ECR → migration task → service          | ⚠️ Written, `push` trigger disabled — not the current deploy |
| **Badge seed**             | `20260831_01` seeds tb_5 with 10 milestones (1d → 365d)               | ✅ Complete |
| **RLS integration tests**  | `test_rls.py`: 12 tests straight against the tables, with a non-bypassing role | ✅ Complete |
| **Models**                 | All 9 SQLAlchemy models                                               | ✅ Complete |
| **Encryption**             | AES-256 field-level encryption                                        | ✅ Complete |
| **Repositories**           | All 9 repositories (full CRUD)                                        | ✅ Complete |
| **Security**               | Encryption, JWT, Blacklist, Rate Limiting, Per-route limits (slowapi) | ✅ Complete |
| **Middleware**             | RateLimit, SecurityHeaders                                            | ✅ Complete |
| **Dependencies**           | getCurrentUser, getDb, getDbWithRLS                                   | ✅ Complete |
| **Exceptions**             | NoHarmException hierarchy                                             | ✅ Complete |
| **FastAPI App**            | main.py with CORS, routes, Socket.IO                                  | ✅ Complete |
| **Schemas**                | All Pydantic DTOs                                                     | ✅ Complete |
| **Services**               | All business logic services                                           | ✅ Complete |
| **Routes**                 | All HTTP endpoints                                                    | ✅ Complete |
| **WebSocket**              | Socket.IO + handlers                                                  | ✅ Complete |
| **Row Level Security**     | Policies in `20260831_02` + per-transaction context                    | ✅ Complete |
| **Account deletion window**| `20260901_01`: `deleted_at` + purgeable FKs, `POST /auth/reactivate`, `purge-accounts` cron | ✅ Complete |
| **Admin authorisation**    | `ADMIN_USER_IDS` allowlist + `getAdminUser` on the status and report routes | ✅ Complete |
| **User reports**           | `20260909_01`: `tb_10` + RLS, `POST /reports/{userId}`, admin queue and resolutions | ✅ Complete |
| **Moderation notices**     | `20260911_04`: `tb_12`, warnings and suspension notices, `POST /users/{id}/warn` | ✅ Complete |
| **Name & picture sanctions**| `20260916_01`: `cl_0h`/`cl_0i`, `PUT /users/{id}/username/reset` and `/picture/{block\|unblock}` | ✅ Complete |
| **Consent records**        | `20260916_02`: `tb_13` + RLS, versioned terms/privacy/health consent, the gate and withdrawal | ✅ Complete |
| **Date of birth**          | `20260916_03`: `cl_0j`, `MINIMUM_AGE_YEARS` enforced at registration   | ✅ Complete |
| **Data export**            | `GET /users/me/export` — the right of access, answered without a ticket | ✅ Complete |
| **Pagination**             | Generic pagination system                                             | ✅ Complete |
| **Unit Tests**             | 1028 tests, 0 failures                                                 | ✅ Complete |
| **Pyright/Pylance config** | `pyrightconfig.json` + `.vscode/settings.json`                        | ✅ Complete |

---

## Component Reference

### Models (`src/infrastructure/database/models/`)

| File                   | Table  | Purpose                             |
| ---------------------- | ------ | ----------------------------------- |
| `userModel.py`         | `tb_0` | User accounts with encrypted fields |
| `streakModel.py`       | `tb_1` | Sobriety streaks                    |
| `friendshipModel.py`   | `tb_2` | Friend relationships                |
| `chatModel.py`         | `tb_3` | Chat conversations                  |
| `messageModel.py`      | `tb_4` | Chat messages                       |
| `badgeModel.py`        | `tb_5` | Achievement badges                  |
| `userBedgesModel.py`   | `tb_6` | User-badge associations             |
| `auditLogsModel.py`    | `tb_7` | Audit trail                         |
| `refreshTokenModel.py` | `tb_8` | Refresh token storage               |
| `reportModel.py`       | `tb_10` | User reports (moderation)          |
| `reportEvidenceModel.py` | `tb_11` | Evidence captured with a report   |
| `moderationNoticeModel.py` | `tb_12` | Warnings and suspension notices  |

### Repositories (`src/infrastructure/database/repositories/`)

| File                        | Entity       | Key Methods                                                       |
| --------------------------- | ------------ | ----------------------------------------------------------------- |
| `userRepository.py`         | User         | findById, findByEmail, findByUsername, create, update, softDelete |
| `streakRepository.py`       | Streak       | findByOwnerId, findCurrentStreak, findCurrentRecord, markAsRecord, updateLastCheckin |
| `friendshipRepository.py`   | Friendship   | findByPair, findAllBySenderId, findAllByReceiverId                |
| `chatRepository.py`         | Chat         | findByParticipants, findAllByUserId                               |
| `messageRepository.py`      | Message      | findByChatId, findUnreadByChatId, markAsRead, markAllAsRead       |
| `badgeRepository.py`        | Badge        | findAll, findById                                                 |
| `userBadgesRepository.py`   | UserBadge    | findByUserId, findByBadgeId, existsByUserAndBadge, grant          |
| `auditLogsRepository.py`    | AuditLogs    | findByType, findByCatalystId, findByDateRange                     |
| `refreshTokenRepository.py` | RefreshToken | findByTokenHash, deleteByUserId, deleteExpired                    |
| `reportRepository.py`       | Report       | findById, findOpenByPair, findByReporter, findAll, countByReported, create, updateStatus |

### Services (`src/domain/services/`)

| File                   | Responsibility                                            |
| ---------------------- | --------------------------------------------------------- |
| `authService.py`       | Registration, login, logout, token refresh, Firebase auth |
| `userService.py`       | Profile management, user search, password changes         |
| `streakService.py`     | Streak lifecycle, check-in tracking, record detection     |
| `friendshipService.py` | Friend requests, accept/reject/block                      |
| `chatService.py`       | Conversation management                                   |
| `messageService.py`    | Message CRUD, read status                                 |
| `badgeService.py`      | Achievement checking and granting                         |
| `userBadgeService.py`  | User-badge management                                     |
| `reportService.py`     | Filing reports, the reporter's own list, admin queue and resolutions |
| `auditLogsService.py`  | Audit trail operations                                    |

### Routes (`src/api/routes/`)

| File                  | Endpoints                                                                              | Auth Required |
| --------------------- | -------------------------------------------------------------------------------------- | ------------- |
| `authRoutes.py`       | POST /auth/register, /auth/login, /auth/refresh, /auth/logout                          | Varies        |
| `userRoutes.py`       | GET /users/me, PUT /users/me, PUT /users/password, GET /users/{userId}                 | Yes           |
| `streakRoutes.py`     | GET /streaks/current, /streaks/record, /streaks/history, POST /streaks/start, /streaks/end, /streaks/checkin | Yes           |
| `friendshipRoutes.py` | GET /friendships, POST /friendships, PUT /friendships/{id}/accept, etc.                | Yes           |
| `chatRoutes.py`       | GET /chats, GET /chats/{chatId}, POST /chats, PUT /chats/{chatId}/read                 | Yes           |
| `messageRoutes.py`    | GET /messages/chat/{chatId}, POST /messages, PUT /messages/{id}, DELETE /messages/{id} | Yes           |
| `badgesRoutes.py`     | GET /badges, GET /badges/all                                                           | Yes           |
| `userBadgesRoutes.py` | GET /user-badges, POST /user-badges, etc.                                              | Yes           |
| `reportRoutes.py`     | POST /reports/{userId}, GET /reports/mine; admin: GET /reports, GET /reports/{id}, PUT /reports/{id}/resolve/{status} | Yes           |
| `auditLogsRoutes.py`  | GET /logs, GET /logs/{logId}, GET /logs/type/{type}, etc.                              | Yes           |

### Schemas (`src/schemas/`)

| File                   | Schemas                                                                         |
| ---------------------- | ------------------------------------------------------------------------------- |
| `authSchemas.py`       | AuthRegisterRequest, AuthLoginRequest, TokenResponse                            |
| `userSchemas.py`       | UserRegisterRequest, UserUpdateRequest, UserPrivateResponse, UserPublicResponse |
| `streakSchemas.py`     | StreakResponse (start_at, end_at, last_checkin), StreakCreate, StreakUpdate     |
| `friendshipSchemas.py` | FriendshipRequest, FriendshipResponse, FriendshipListResponse                   |
| `chatSchemas.py`       | ChatResponse, ConversationResponse                                              |
| `messageSchemas.py`    | MessageRequest, MessageResponse, MessageListResponse                            |
| `badgeSchemas.py`      | BadgeResponse, BadgeListResponse                                                |
| `userBadgeSchemas.py`  | UserBadgeResponse, UserBadgeCreate, UserBadgeListResponse                       |
| `reportSchemas.py`     | ReportReason, ReportRequest, ReportResponse, ReportListResponse                 |
| `auditLogsSchemas.py`  | AuditLogsResponse, AuditLogsCreate, AuditLogsListResponse                       |
| `paginationSchemas.py` | PaginationParams, PaginatedResponse[T]                                          |

### WebSocket (`src/websocket/`)

| File                           | Purpose                                                      |
| ------------------------------ | ------------------------------------------------------------ |
| `socketManager.py`             | Socket.IO server, JWT auth on connect, connection management |
| `handlers/chatHandlers.py`     | Real-time messaging events                                   |
| `handlers/presenceHandlers.py` | Online/offline status, typing indicators                     |

### Security (`src/security/`)

| File                     | Purpose                                              |
| ------------------------ | ---------------------------------------------------- |
| `jwtHandler.py`          | Access/refresh token generation and validation       |
| `tokenBlacklist.py`      | JWT revocation with persistent storage               |
| `persistentHashTable.py` | Append-only log for blacklist                        |
| `rateLimiter.py`         | IP-based and login rate limiting (global middleware) |
| `limiter.py`             | Shared `slowapi` Limiter for per-route rate limits   |
| `middleware.py`          | RateLimitMiddleware, SecurityHeadersMiddleware       |
| `encryption.py`          | AES-256, Argon2, SHA-256                             |
| `sanitizer.py`           | HTML sanitization via bleach                         |

---

## What is Missing / Empty

| Component           | Status   | Notes                              |
| ------------------- | -------- | ---------------------------------- |
| Terms of Use / Privacy Policy **text** | ⬜ Draft | Every section in `noHarm/src/screens/legal/legalContent.js` and in `noHarm/public/{terms,privacy}.html` is a placeholder, and `draft: true` is what makes the app say so rather than presenting an empty page as terms. The machinery around them is finished: publishing is writing the sections, mirroring them into the two public files, flipping `draft`, and bumping `TERMS_VERSION` / `PRIVACY_VERSION` here — which is what asks every existing account to accept. |
| `storageService.py` | ⬜ Empty | File uploads, profile pictures. The module holds the declarative `Base` and nothing else. `STORAGE_SERVICE_URI`, `STORAGE_SERVICE_KEY` and `STORAGE_PATH` have been removed from `core/config.py`; whoever builds uploads adds the settings the implementation actually needs. |
| Backups off the database disk | ⬜ Missing | `backup-db.sh` writes to `~/backups`, on the **same EBS volume** as Postgres. It covers accidental deletion, not loss of the volume. Shipping to S3 requires an instance role — there is no AWS credential on the machine today. |
| Monitoring / alerting | ⬜ Missing | Nothing warns when a container dies, the dump fails, the certificate renewal does not run, or `purge-accounts` stops purging. All three cron jobs only write to a log — and a purge that never runs is invisible from outside, because a deleted account past its window answers "Account not found." either way. |

---

## Architecture

### Clean Architecture Layers

```
HTTP Request
    │
    ▼
Route (src/api/routes/)        — validates schema (Pydantic) · extracts JWT
    │
    ▼
Service (src/domain/services/)   — applies business rules · orchestrates repositories
    │
    ▼
Repository (src/infrastructure/database/repositories/) — executes database queries
    │
    ▼
Model (src/infrastructure/database/models/) — ORM maps table ↔ Python object
    │
    ▼
PostgreSQL
```

### Dependencies Flow

- Routes depend on Services
- Services depend on Repositories
- Repositories depend on Models
- All depend on Encryption utility

### Key Features

1. **Field-Level Encryption**: All sensitive fields encrypted at rest with AES-256 (Fernet)
2. **Row Level Security**: PostgreSQL RLS policies enforce data access control at database level
3. **JWT Authentication**: Access tokens (15 min) + Refresh tokens (7 days) with blacklist
4. **Rate Limiting**: Two-layer — global IP floor (60 req/min via middleware) + per-route ceilings via `slowapi` (5/min on register, 10/min on login, etc.)
5. **Pagination**: Generic pagination system with PaginatedResponse[T]
6. **WebSocket**: Real-time chat with Socket.IO and JWT authentication

---

## Status Codes

Defined in `.secrets.toml` under `STATUS_CODES`:

| Name       | Value | Used For            |
| ---------- | ----- | ------------------- |
| `disabled` | 0     | User, streak, badge |
| `enabled`  | 1     | User, streak        |
| `deleted`  | 2     | Soft delete         |
| `blocked`  | 3     | User account        |
| `pending`  | 4     | Friendship request · unreviewed report |
| `accepted` | 5     | Friendship · report actioned |
| `ignored`  | 6     | Friendship · report dismissed |
| `unread`   | 7     | Message             |
| `read`     | 8     | Message             |
| `banned`   | 9     | User account        |

---

## Known Issues

1. ~~**Bug in `userBedgesModel.py`**~~ — does not exist: `badge_id` references `tb_5.cl_5a` both in the model and in the baseline. The real error was `UserModel.user_badges` declaring the relationship by string: the name only resolves if the class's module has been imported. `models/__init__.py` now imports all ten, and `patch_orm_models` is no longer autouse.
2. **User ID type**: `tb_0.cl_0a` (and all FK columns referencing it) use `String`/`VARCHAR`, not `UUID`. Firebase UID is the PK. Other tables (`tb_1`–`tb_8`) still use `UUID(as_uuid=True)` for their own PKs.

---

## Unimplementable Rules Summary

Rules requiring infrastructure changes (new tables, models, external services):

| Rule                           | Description                            | Blocked By                                         |
| ------------------------------ | -------------------------------------- | -------------------------------------------------- |
| 1.1 — Email Verification       | Backend-initiated verification flow    | `emailService.py` empty; needs token storage table |
| ~~7.2 — Badge Milestones~~     | Auto-grant at streak milestones        | ✅ Desbloqueado pela migration `20260831_01`       |
| 8.1 — Audit Log Password/Email | Type=3 (password), Type=4 (email) logs | Auth delegated to Firebase — no backend endpoints  |

See `docs/UNIMPLEMENTABLE_RULES.md` for full details.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure secrets
cp .env.example .secrets.toml
# Edit .secrets.toml with your values

# Run migrations — mandatory: nothing creates the schema at startup, and
# without them the database has no RLS policies
APP_ENV=alembic alembic upgrade head

# Start server
cd src && python run.py
```

See `README.md` for full documentation.
