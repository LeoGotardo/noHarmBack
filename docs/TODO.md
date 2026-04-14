# NoHarm Backend — Implementation Status

This document tracks the current state of the backend architecture and components.

---

## Current State

### What is Done ✅

| Layer | Component | Status |
|-------|-----------|--------|
| **Project Structure** | Clean Architecture (4 layers) | ✅ Complete |
| **Configuration** | Dynaconf multi-environment | ✅ Complete |
| **Database** | SQLAlchemy engine + session | ✅ Complete |
| **Migrations** | Alembic setup | ✅ Complete |
| **Deployment** | Vercel + Neon config | ✅ Complete |
| **Models** | All 9 SQLAlchemy models | ✅ Complete |
| **Encryption** | AES-256 field-level encryption | ✅ Complete |
| **Repositories** | All 9 repositories (full CRUD) | ✅ Complete |
| **Security** | Encryption, JWT, Blacklist, Rate Limiting | ✅ Complete |
| **Middleware** | RateLimit, SecurityHeaders | ✅ Complete |
| **Dependencies** | getCurrentUser, getDb, getDbWithRLS | ✅ Complete |
| **Exceptions** | NoHarmException hierarchy | ✅ Complete |
| **FastAPI App** | main.py with CORS, routes, Socket.IO | ✅ Complete |
| **Schemas** | All Pydantic DTOs | ✅ Complete |
| **Services** | All business logic services | ✅ Complete |
| **Routes** | All HTTP endpoints | ✅ Complete |
| **WebSocket** | Socket.IO + handlers | ✅ Complete |
| **Row Level Security** | PostgreSQL RLS policies | ✅ Complete |
| **Pagination** | Generic pagination system | ✅ Complete |

---

## Component Reference

### Models (`src/infrastructure/database/models/`)

| File | Table | Purpose |
|------|-------|---------|
| `userModel.py` | `tb_0` | User accounts with encrypted fields |
| `streakModel.py` | `tb_1` | Sobriety streaks |
| `friendshipModel.py` | `tb_2` | Friend relationships |
| `chatModel.py` | `tb_3` | Chat conversations |
| `messageModel.py` | `tb_4` | Chat messages |
| `badgeModel.py` | `tb_5` | Achievement badges |
| `userBedgesModel.py` | `tb_6` | User-badge associations |
| `auditLogsModel.py` | `tb_7` | Audit trail |
| `refreshTokenModel.py` | `tb_8` | Refresh token storage |

### Repositories (`src/infrastructure/database/repositories/`)

| File | Entity | Key Methods |
|------|--------|-------------|
| `userRepository.py` | User | findById, findByEmail, findByUsername, create, update, softDelete |
| `streakRepository.py` | Streak | findByOwnerId, findCurrentStreak, findCurrentRecord, markAsRecord |
| `friendshipRepository.py` | Friendship | findByPair, findAllBySenderId, findAllByReceiverId |
| `chatRepository.py` | Chat | findByParticipants, findAllByUserId |
| `messageRepository.py` | Message | findByChatId, findUnreadByChatId, markAsRead, markAllAsRead |
| `badgeRepository.py` | Badge | findAll, findById |
| `userBadgesRepository.py` | UserBadge | findByUserId, findByBadgeId, existsByUserAndBadge, grant |
| `auditLogsRepository.py` | AuditLogs | findByType, findByCatalystId, findByDateRange |
| `refreshTokenRepository.py` | RefreshToken | findByTokenHash, deleteByUserId, deleteExpired |

### Services (`src/domain/services/`)

| File | Responsibility |
|------|----------------|
| `authService.py` | Registration, login, logout, token refresh, Firebase auth |
| `userService.py` | Profile management, user search, password changes |
| `streakService.py` | Streak lifecycle, expiry check, record tracking |
| `friendshipService.py` | Friend requests, accept/reject/block |
| `chatService.py` | Conversation management |
| `messageService.py` | Message CRUD, read status |
| `badgeService.py` | Achievement checking and granting |
| `userBadgeService.py` | User-badge management |
| `auditLogsService.py` | Audit trail operations |

### Routes (`src/api/routes/`)

| File | Endpoints | Auth Required |
|------|-----------|---------------|
| `authRoutes.py` | POST /auth/register, /auth/login, /auth/refresh, /auth/logout | Varies |
| `userRoutes.py` | GET /users/me, PUT /users/me, PUT /users/password, GET /users/{userId} | Yes |
| `streakRoutes.py` | GET /streaks/current, /streaks/record, /streaks/history, POST /streaks/end | Yes |
| `friendshipRoutes.py` | GET /friendships, POST /friendships, PUT /friendships/{id}/accept, etc. | Yes |
| `chatRoutes.py` | GET /chats, GET /chats/{chatId}, POST /chats, PUT /chats/{chatId}/read | Yes |
| `messageRoutes.py` | GET /messages/chat/{chatId}, POST /messages, PUT /messages/{id}, DELETE /messages/{id} | Yes |
| `badgesRoutes.py` | GET /badges, GET /badges/all | Yes |
| `userBadgesRoutes.py` | GET /user-badges, POST /user-badges, etc. | Yes |
| `auditLogsRoutes.py` | GET /logs, GET /logs/{logId}, GET /logs/type/{type}, etc. | Yes |

### Schemas (`src/schemas/`)

| File | Schemas |
|------|---------|
| `authSchemas.py` | AuthRegisterRequest, AuthLoginRequest, TokenResponse |
| `userSchemas.py` | UserRegisterRequest, UserUpdateRequest, UserPrivateResponse, UserPublicResponse |
| `streakSchemas.py` | StreakResponse, StreakResetRequest |
| `friendshipSchemas.py` | FriendshipRequest, FriendshipResponse, FriendshipListResponse |
| `chatSchemas.py` | ChatResponse, ConversationResponse |
| `messageSchemas.py` | MessageRequest, MessageResponse, MessageListResponse |
| `badgeSchemas.py` | BadgeResponse, BadgeListResponse |
| `userBadgeSchemas.py` | UserBadgeResponse, UserBadgeCreate, UserBadgeListResponse |
| `auditLogsSchemas.py` | AuditLogsResponse, AuditLogsCreate, AuditLogsListResponse |
| `paginationSchemas.py` | PaginationParams, PaginatedResponse[T] |

### WebSocket (`src/websocket/`)

| File | Purpose |
|------|---------|
| `socketManager.py` | Socket.IO server, JWT auth on connect, connection management |
| `handlers/chatHandlers.py` | Real-time messaging events |
| `handlers/presenceHandlers.py` | Online/offline status, typing indicators |

### Security (`src/security/`)

| File | Purpose |
|------|---------|
| `jwtHandler.py` | Access/refresh token generation and validation |
| `tokenBlacklist.py` | JWT revocation with persistent storage |
| `persistentHashTable.py` | Append-only log for blacklist |
| `rateLimiter.py` | IP-based and login rate limiting |
| `middleware.py` | RateLimitMiddleware, SecurityHeadersMiddleware |
| `encryption.py` | AES-256, Argon2, SHA-256 |
| `sanitizer.py` | HTML sanitization via bleach |

---

## What is Missing / Empty

| Component | Status | Notes |
|-----------|--------|-------|
| `emailService.py` | ⬜ Empty | Email verification, password reset |
| `storageService.py` | ⬜ Empty | File uploads, profile pictures |

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
4. **Rate Limiting**: IP-based (60 req/min) and login brute-force protection
5. **Pagination**: Generic pagination system with PaginatedResponse[T]
6. **WebSocket**: Real-time chat with Socket.IO and JWT authentication

---

## Status Codes

Defined in `.secrets.toml` under `STATUS_CODES`:

| Name | Value | Used For |
|------|-------|----------|
| `disabled` | 0 | User, streak, badge |
| `enabled` | 1 | User, streak |
| `deleted` | 2 | Soft delete |
| `blocked` | 3 | User account |
| `pending` | 4 | Friendship request |
| `accepted` | 5 | Friendship |
| `ignored` | 6 | Friendship |
| `unread` | 7 | Message |
| `read` | 8 | Message |
| `banned` | 9 | User account |

---

## Known Issues

1. **Bug in `userBedgesModel.py`**: `badge_id` foreign key references `tb_1.cl_1a` instead of `tb_5.cl_5a`

---

## Unimplementable Rules Summary

Rules requiring infrastructure changes (new tables, models, external services):

| Rule | Description | Blocked By |
|------|-------------|------------|
| 1.1 — Email Verification | Backend-initiated verification flow | `emailService.py` empty; needs token storage table |
| 2.2 — Refresh Token DB Storage | Hashed tokens in DB with device hints | Needs `tb_8` model, migration, repository |
| 7.2 — Badge Milestones | Auto-grant at streak milestones | Badge seed data missing in `tb_5` |
| 8.1 — Audit Log Password/Email | Type=3 (password), Type=4 (email) logs | Auth delegated to Firebase — no backend endpoints |

See `docs/UNIMPLEMENTABLE_RULES.md` for full details.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure secrets
cp .env.example .secrets.toml
# Edit .secrets.toml with your values

# Run migrations
ENV=development alembic upgrade head

# Start server
cd src && python run.py
```

See `README.md` for full documentation.
