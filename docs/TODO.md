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
| **RLS integration tests**  | `test_rls.py`: 35 tests straight against the tables, with a non-bypassing role | ✅ Complete |
| **Models**                 | One per table, `tb_0`–`tb_19` (`tb_8` is defined but never written) | ✅ Complete |
| **Encryption**             | AES-GCM column encryption + keyed blind indexes | ✅ Complete |
| **Repositories**           | One per table that the app reads or writes      | ✅ Complete |
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
| **Admin authorisation**    | `ADMIN_USER_IDS`, official accounts and `tb_19` grants, read by `core/roles.isAdmin` through `getAdminUser` | ✅ Complete |
| **User reports**           | `20260909_01`: `tb_10` + RLS, `POST /reports/{userId}`, admin queue and resolutions | ✅ Complete |
| **Moderation notices**     | `20260911_04`: `tb_12`, warnings and suspension notices, `POST /users/{id}/warn` | ✅ Complete |
| **Name & picture sanctions**| `20260916_01`: `cl_0h`/`cl_0i`, `PUT /users/{id}/username/reset` and `/picture/{block\|unblock}` | ✅ Complete |
| **Consent records**        | `20260916_02`: `tb_13` + RLS, versioned terms/privacy/health consent, the gate and withdrawal | ✅ Complete |
| **Date of birth**          | `20260916_03`: `cl_0j`, `MINIMUM_AGE_YEARS` enforced at registration   | ✅ Complete |
| **Data export**            | `GET /users/me/export` — the right of access, answered without a ticket | ✅ Complete |
| **Pagination**             | Generic pagination system                                             | ✅ Complete |
| **Unit Tests**             | ~1150 tests, 0 failures (`pytest tests/unit -q` for the current number) | ✅ Complete |
| **Pyright/Pylance config** | `pyrightconfig.json` + `.vscode/settings.json`                        | ✅ Complete |

---

## Component Reference

The per-file tables — models, repositories, services, routes, schemas,
security, WebSocket — live in [`README.md`](README.md), "Source Code". They
were duplicated here and the two copies drifted apart; there is now one.

---

## What is Missing / Empty

| Component           | Status   | Notes                              |
| ------------------- | -------- | ---------------------------------- |
| Terms of Use / Privacy Policy **text** | ✅ Complete | In force since 2026-09-28 (`TERMS_VERSION` / `PRIVACY_VERSION` = `"2026-09-28"`). Written from the code, not reviewed by a lawyer yet — worth doing, because of the health-data consent. |
| `storageService.py` | ⬜ Empty | File uploads, profile pictures. The module holds the declarative `Base` and nothing else. `STORAGE_SERVICE_URI`, `STORAGE_SERVICE_KEY` and `STORAGE_PATH` have been removed from `core/config.py`; whoever builds uploads adds the settings the implementation actually needs. |
| Backups off the database disk | ⬜ Missing | `backup-db.sh` writes to `~/backups`, on the **same EBS volume** as Postgres. It covers accidental deletion, not loss of the volume. Shipping to S3 requires an instance role — there is no AWS credential on the machine today. |
| Monitoring / alerting | ⬜ Missing | Nothing pages anyone when a container dies, the dump fails or the certificate renewal does not run. The cron jobs only write to a log; the admin board's health panel shows a stalled purge, but only to someone who opens it — and a purge that never runs is invisible from outside, because a deleted account past its window answers "Account not found." either way. |

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

1. **Field-Level Encryption**: Sensitive columns encrypted at rest with AES-GCM (`StringEncryptedType`), keyed blind indexes for lookups
2. **Row Level Security**: PostgreSQL RLS policies enforce data access control at database level
3. **JWT Authentication**: Access tokens (15 min) + Refresh tokens (7 days) with blacklist
4. **Rate Limiting**: Two-layer, both in Redis — global IP floor (240 req/min via middleware) + per-route ceilings via `slowapi` (5/min on register, 10/min on login, etc.)
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

1. ~~**Bug in `userBadgesModel.py`**~~ — does not exist: `badge_id` references `tb_5.cl_5a` both in the model and in the baseline. The real error was `UserModel.user_badges` declaring the relationship by string: the name only resolves if the class's module has been imported. `models/__init__.py` now imports all ten, and `patch_orm_models` is no longer autouse.
2. **User ID type**: `tb_0.cl_0a` (and all FK columns referencing it) use `String`/`VARCHAR`, not `UUID`. Firebase UID is the PK. Other tables (`tb_1`–`tb_8`) still use `UUID(as_uuid=True)` for their own PKs.

---

## Unimplementable Rules Summary

Rules requiring infrastructure changes (new tables, models, external services):

| Rule                           | Description                            | Blocked By                                         |
| ------------------------------ | -------------------------------------- | -------------------------------------------------- |
| 1.1 — Email Verification       | Backend-initiated verification flow    | No email service exists (Firebase sends email); would need one plus a token table |
| ~~7.2 — Badge Milestones~~     | Auto-grant at streak milestones        | ✅ Desbloqueado pela migration `20260831_01`       |
| 8.1 — Audit Log Password/Email | Type=3 (password), Type=4 (email) logs | Auth delegated to Firebase — no backend endpoints  |

The same table, with the reasoning, is in `security.md` §10.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements-dev.txt

# Configure secrets: create .secrets.toml with a [dev] section
# (see README.md, Configuration — there is no template file)

# Run migrations — mandatory: nothing creates the schema at startup, and
# without them the database has no RLS policies
APP_ENV=alembic alembic upgrade head

# Start server
cd src && python run.py
```

See `README.md` for full documentation.
