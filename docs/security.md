# Security Guide — NoHarm Backend

This document describes every attack vector considered during the design of the NoHarm backend, the countermeasures implemented, and those still pending. It serves as both a reference and a checklist for security audits.

---

## Table of Contents

1. [Authentication Attacks](#1-authentication-attacks)
2. [Injection Attacks](#2-injection-attacks)
3. [Session Attacks](#3-session-attacks)
4. [Denial of Service](#4-denial-of-service)
5. [Data Attacks](#5-data-attacks)
6. [WebSocket Attacks](#6-websocket-attacks)
7. [Account & Identity Attacks](#7-account--identity-attacks)
8. [Infrastructure & Configuration Risks](#8-infrastructure--configuration-risks)
9. [Supply Chain & Dependency Risks](#9-supply-chain--dependency-risks)
10. [Implementation Status](#10-implementation-status)

---

## 1. Authentication Attacks

### 1.1 JWT Token Theft

**What it is:** An attacker steals the victim's JWT and impersonates them.

**Attack vectors:**
- XSS extracts the token from `localStorage`
- Man-in-the-middle on plain HTTP
- Malware on the device

**Countermeasures implemented (`src/security/jwtHandler.py`):**

| Measure | Detail |
|---------|--------|
| Short-lived access token | 15-minute expiry — stolen tokens expire quickly |
| Long-lived refresh token | 7-day expiry — issued only on login |
| Unique JTI per token | Every token has a `jti` claim; allows individual revocation |
| Token type enforcement | `verifyToken()` checks the `type` claim matches the expected type |
| Persistent blacklist | Revoked JTIs are stored hashed (SHA-256) in Redis with TTL-based auto-expiry via `TokenBlacklist` |
| Refresh token rotation | Old refresh token JTI is revoked (blacklisted) before new tokens are issued in `authService.refresh()` |

**Token lifecycle:**
```
Login → issue accessToken (15 min) + refreshToken (7 days)
        │
        ├─ Each request → verify accessToken → check blacklist
        │
        └─ On expiry → POST /auth/refresh → verify refreshToken
                                      → revoke old refreshToken (blacklist)
                                      → issue new accessToken + new refreshToken

Logout → revoke accessToken + revoke refreshToken → both added to blacklist
```

**Blacklist implementation (`src/security/tokenBlacklist.py`):**

The blacklist uses **Redis** via `redis.from_url` — in the live deployment a
container on the same host, reached over the compose network as
`redis://redis:6379/0` and never published (see `docs/operations.md`). Each `add` call computes TTL as `(expiresAt − now)` and stores the key via `SETEX` — Redis automatically removes expired keys, so no manual cleanup is needed. JTIs are stored as SHA-256 hashes (`jti:<hash>`) — plaintext JTIs are never written to the store. `isBlacklisted` is an O(1) Redis `EXISTS` check. This replaces the previous file-based `PersistentHashTable` approach, which was not suitable for an ephemeral container filesystem or for running more than one instance.

---

### 1.2 Brute Force Login

**What it is:** An attacker tries thousands of password combinations until one succeeds.

**Countermeasures implemented (`src/security/rateLimiter.py`):**

`LoginRateLimiter` — per-UID sliding window (Firebase UID, not username):

| Configuration | Value |
|---------------|-------|
| Window | 15 minutes |
| Max attempts | 5 |
| Lockout duration | 30 minutes |
| Reset on success | Yes — `onSuccess(username)` clears the attempt history |

`IpRateLimiter` — per-IP sliding window, in Redis:

| Configuration | Value |
|---------------|-------|
| Window | 60 seconds (`RATE_LIMIT_WINDOW_SECONDS`) |
| Max requests | 240 (`RATE_LIMIT_MAX_REQUESTS`) |
| Block duration | 60 s on the first breach, doubling on repeat, capped at 900 s (`RATE_LIMIT_BLOCK_SECONDS`, `RATE_LIMIT_MAX_BLOCK_SECONDS`) |

**Not applicable:** there is no password to guess. Login takes a Firebase ID
token, which only Google issues after its own sign-in (with its own rate
limits, CAPTCHA and 2FA). A timing difference or a CAPTCHA here would protect
nothing an attacker can try.

---

## 2. Injection Attacks

### 2.1 SQL Injection

**What it is:** An attacker injects malicious SQL through user inputs.

**Countermeasures implemented:**

- **SQLAlchemy ORM** is used exclusively — parameters are automatically escaped
- **Pydantic schemas** validate and type-check all inputs before they reach the repository layer
- Raw SQL (`text()`) is never used in any repository

**Example of safe query (ORM):**
```python
# Attacker input: "admin' OR '1'='1' --"
user = session.query(UserModel).filter(UserModel.email == email).first()
# SQLAlchemy binds the value as a parameter — the injection string is treated as a literal
```

---

### 2.2 XSS (Cross-Site Scripting)

**What it is:** An attacker injects malicious JavaScript that executes in other users' browsers.

**Countermeasures implemented:**

`src/security/sanitizer.py` — `Sanitizer.cleanHtml()`:
- Strips all HTML tags via `bleach` (`ALLOWED_TAGS = {}`)
- Applied to any user-supplied free-text before persistence

`src/security/middleware.py` — `SecurityHeadersMiddleware`:

| Header | Value |
|--------|-------|
| `Content-Security-Policy` | `default-src 'self'` + per-resource restrictions |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `X-XSS-Protection` | `1; mode=block` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |

**Implemented:** `Sanitizer.cleanHtml()` is applied in:
- `authService.register()` — username on registration
- `userService.updateProfile()` — username on update
- `messageService.sendMessage()` — message content before persistence

Also applied since: post and comment content (`PostService._clean`), report
details and notes (`ReportService`), moderator messages (`NoticeService`).
Usernames are restricted to `[a-zA-Z0-9_-]` instead.

**Rule for new fields:** any new user-supplied free text goes through
`Sanitizer.cleanHtml()` before persistence.

---

### 2.3 Mass Assignment

**What it is:** An attacker includes extra fields in a request body (e.g. `"isAdmin": true`) that should not be settable by regular users.

**Countermeasures implemented:**

Pydantic schemas act as an explicit whitelist. Only fields declared in a schema can be updated. FastAPI ignores any extra fields by default.

**Schemas with `extra="forbid"`:** every single-entity response (`AuthResponse`, `UserResponse`, `MeResponse`, `StreakResponse`, `ChatResponse`, `FriendshipResponse`, `MessageResponse`, `BadgeResponse`, `UserBadgeResponse`, `AuditLogsResponse`, the report, notice, consent and post responses) and the request bodies where an extra field would be an attack — `ReportRequest` (no message text), `ConsentAcceptRequest` (no version), the post and comment bodies.

**Every request body refuses unknown fields** (422): the auth bodies, `ProfileUpdateRequest`, the streak bodies, `BadgeUpdate`, `UserBadgeUpdate`, and the bodies declared in the route files (`ChatCreateRequest`, `SendMessageRequest`, `BroadcastRequest`, `DeviceBody`, `UpdateDeviceBody`). A register body still carrying `uid`/`email` — the old identity fields — is refused rather than trimmed.

Internal `*Create`/`*Update` schemas that no route accepts are not covered; they never see client input.

---

## 3. Session Attacks

### 3.1 CSRF (Cross-Site Request Forgery)

**What it is:** A malicious site triggers authenticated requests to the API on behalf of the victim.

**Current posture:** The API uses JWT in the `Authorization: Bearer` header, not cookies. Browser-based CSRF attacks cannot forge this header — the attacker would need JavaScript access to the token, which is prevented by CORS and XSS protections.

**Pending countermeasures (for future cookie-based flows):**
- [ ] Double-submit cookie pattern if cookies are introduced
- [ ] `SameSite=Strict` on any cookies
- [ ] Validate `Origin` / `Referer` on state-changing endpoints

---

### 3.2 CORS Misconfiguration

**What it is:** Overly permissive CORS allows arbitrary origins to read API responses.

**Countermeasures implemented (`src/main.py`):**

```python
allow_origins = config.ALLOWED_ORIGINS   # Explicit whitelist per environment
allow_methods = ["GET", "POST", "PUT", "DELETE"]
allow_headers = ["Authorization", "Content-Type"]
```

In `development`, `ALLOWED_ORIGINS = ["*"]` is acceptable. In `staging` and `production` it is restricted to the app's origin.

---

## 4. Denial of Service

### 4.1 Application-Layer DoS / Brute Force

**Countermeasures implemented (`src/security/rateLimiter.py`, `src/security/middleware.py`, `src/security/limiter.py`):**

`RateLimitMiddleware` applies `IpRateLimiter` globally on every request:
- 240 requests / 60 seconds per IP
- Excess requests → 429 with `Retry-After`
- The block starts at 60 s and doubles on repeat breaches, up to 900 s

`LoginRateLimiter` applies per-UID limits on the login endpoint (see §1.2).

**Per-route rate limits via `slowapi` (`src/security/limiter.py`):**

Every HTTP endpoint carries a `@limiter.limit(...)` decorator. The shared `Limiter` instance uses the same X-Forwarded-For aware IP extraction as `RateLimitMiddleware`. The global middleware acts as a floor; per-route decorators enforce tighter ceilings on sensitive paths.

| Tier | Endpoints | Limit |
|------|-----------|-------|
| Critical | `POST /auth/register` | 5/minute |
| High | `POST /auth/login` | 10/minute |
| High | `POST /auth/refresh`, `POST /auth/logout` | 20/minute |
| Write | create/update/delete mutations across all routes | 5–10/minute |
| Read | all GET endpoints | 30–60/minute |

Exceeding a per-route limit returns 429. All of it — `slowapi`, `IpRateLimiter`, `LoginRateLimiter` and the JWT blacklist — keeps its state in Redis, shared across workers and instances (§8.2).

**Pending countermeasures:**
- [ ] Burst protection (e.g. max 10 requests/second before sliding window kicks in)

---

### 4.2 Slowloris / Connection Exhaustion

**What it is:** Attacker keeps thousands of connections half-open, exhausting server threads.

**In place** (`docker/nginx.conf`): `client_header_timeout 10s`,
`client_body_timeout 10s`, `send_timeout 30s`, `keepalive_timeout 15s`, and
request bodies capped at 64 KB (1 MB on `/ws/`). uvicorn listens on loopback
only, behind nginx, with its default 5 s keep-alive.

`limit_concurrency` is deliberately not set: uvicorn counts open WebSockets
against it, so a cap sized for HTTP would start refusing sockets first.

---

## 5. Data Attacks

### 5.1 Data Exposure

**What it is:** Sensitive data leaks through API responses, logs, or error messages.

**Countermeasures implemented:**

**Field-level encryption at rest** (`src/security/encryption.py`):
- Sensitive columns (username, email, message content, timestamps, report details, post content, …) are encrypted with AES-GCM by `sqlalchemy_utils`' `StringEncryptedType`, under `DATABASE_ENCRYPTION_KEY`
- Obfuscated column names (`cl_0a`, `cl_0b`, ...) add an additional layer of obscurity
- The columns looked up by equality (username, email, device token) carry a parallel `_h` column: an HMAC-SHA256 blind index under `BLIND_INDEX_KEY`

**Response filtering:**
- Pydantic `response_model` on every route ensures only declared fields are returned
- Another user is always `UserResponse` (id, username, picture, timestamps, role); e-mail and status exist only on `MeResponse`. Routes never return a domain entity directly — `GET /users?paginated=true` once returned the `User` entity, e-mail and birth date included, to any signed-in account
- `passwordHash` and internal columns are never included in any response schema

**Pending countermeasures:**
- [ ] Structured log sanitisation — ensure no sensitive values appear in log output
- [ ] Add `response_model_exclude_unset=True` where appropriate to avoid leaking default values

---

### 5.2 Insecure Direct Object Reference (IDOR)

**What it is:** A user accesses another user's resources by guessing or iterating resource IDs.

**Countermeasures implemented:**
- User PKs (`tb_0.cl_0a`) are **Firebase UIDs** (opaque strings, not guessable). All other PKs (`tb_1`–`tb_10`) are **UUID v4**.
- `getCurrentUser` dependency injects the authenticated user's ID into every protected route
- Ownership checks implemented in all `Service` methods:
  - `ChatService._assertParticipant()` — enforced on `get`, `activate`, `endChat`, `delete`
  - `MessageService.sendMessage` / `markAsRead` / `markAllAsRead` — verifies sender is a chat participant
  - `FriendshipService.accept` / `reject` / `block` / `unblock` / `delete` — verifies requester is a participant
  - `UserService.delete` — only the account owner may delete their own account
  - `StreakService.checkin` — verifies `owner_id == userId`

---

## 6. WebSocket Attacks

### 6.1 WebSocket Hijacking / Unauthenticated Connections

**What it is:** An attacker connects to the WebSocket endpoint without a valid token.

**Countermeasures implemented (`src/websocket/socketManager.py`):**

| Measure | Detail |
|---------|--------|
| Mandatory JWT auth | `connect` event extracts token from `auth` dict or query string, rejects connection if invalid |
| User session binding | `sio.save_session(sid, {"userId": userId})` stores authenticated user |
| Room isolation | Users join personal room `user_{userId}` on connect; chat rooms `chat_{chatId}` joined via events |
| Presence tracking | Registry in Redis, multi-device and shared across instances |
| Event rate limits | `@wsLimit` per user: `send_message` 30/min, `typing` 60/min |
| Connection cap | 3 sockets per user (`WsConnectionLimiter`, a Redis sorted set of sid → connect time). A fourth is accepted and the **oldest** is told `session_replaced` and disconnected; a stale entry from a dead worker is just the oldest, so the set heals itself |
| Payload size | `max_http_buffer_size` 2 MB on the server; message content capped at 2000 characters in `MessageService.sendMessage`, shared with the REST path |



---

## 7. Account & Identity Attacks

### 7.1 Account Enumeration

**What it is:** An attacker probes the API to discover which email addresses are registered, building a list for targeted attacks (phishing, credential stuffing).

**How it happens:**
- `POST /auth/login` returns `"User not found"` for unknown emails and `"Invalid password"` for known ones — the attacker can tell the difference
- `POST /auth/register` returns a conflict error for duplicate emails — confirming the email is taken
- Forgot-password flows that confirm whether the email exists

**Why this matters for NoHarm:** Users are in addiction recovery. Confirming their presence on the platform to a third party is a privacy violation with real personal-safety implications.

**Countermeasures implemented:**
- `authService.login()` returns generic `"Invalid credentials."` (401) when the user is **not found** — attacker cannot confirm whether a UID is registered
- `authService.register()` returns generic `"Registration failed. Please check your details."` (409) for both email and username conflicts — neither conflicting field is identified in the response

**Note:** Banned, blocked, and deleted accounts return **specific 403 responses** (`ACCOUNT_BANNED`, `ACCOUNT_BLOCKED`, `ACCOUNT_DELETED`, `ACCOUNT_PENDING_DELETION`) after the user record is found. This is intentional — these are post-authentication status checks, not enumeration vectors, since an attacker must already possess the valid UID. The trade-off is accepted.

`ACCOUNT_PENDING_DELETION` carries one extra field, `details.deletionScheduledAt`, and it is the only status response that tells the caller anything they did not already know: that the account they hold a verified Firebase token for is restorable, and until when. It requires the same proof as a login, so it leaks nothing to anyone who is not the account holder.

~~`authService.register()` proceeded to create the user when a uniqueness lookup failed with a non-404 error.~~ **Fixed** — every lookup (`findById`, `findByEmail`, `findByUsername`) now re-raises anything that is not a 404.

~~`GET /users?search=` matched an exact e-mail too, confirming to any signed-in account that an address had an account.~~ **Fixed** — it matches usernames only (`UserRepository.search`).

~~`userService.getPublicProfile()` swallowed non-404 errors from `findByUsers`, which could allow a blocked user to view a blocker's profile during a DB transient error.~~ **Fixed** — service now re-raises any non-404 exception from `findByUsers`.



**Where to implement:** `authRoutes.py`

---

### 7.2 Email Verification (Firebase Auth)

**Status:** Implemented via Firebase Authentication

**How it works:**
- Users register and verify email via Firebase Auth (frontend)
- Backend receives Firebase identity data including `emailVerified` flag
- On registration: `status = enabled` if `emailVerified`, else `status = pending`
- `pending` is **recorded, not enforced** at the door: `getCurrentUser` rejects only deleted, banned and blocked accounts. What it gates is filing reports (`REPORTER_NOT_ELIGIBLE`) and writing posts (`POSTER_NOT_ELIGIBLE`), both of which require `enabled`. Google sign-in always arrives verified, so in practice no account is `pending`

**Countermeasures implemented:**
- Email ownership verified by Firebase (Google infrastructure)
- `status` field controls access to protected resources
- Duplicate email check prevents account enumeration (returns generic 409)

**Note:** There is no email service in the backend — Firebase sends the verification email.

---

### 7.3 Password Reset (Firebase Auth)

**Status:** Handled by Firebase Authentication

Firebase Auth manages password reset flows. The backend does not store or manage passwords — authentication is delegated to Firebase.

**Firebase handles:**
- Password reset email sending
- Secure token generation and validation
- Token expiry and single-use enforcement

**Where Firebase manages:** Firebase Console / Authentication settings

---

### 7.4 Refresh Token Persistence

**Status:** Partially implemented — model exists, repository does not.

**What exists:**
- `refreshTokenModel.py` defines `tb_8` with fields `userId`, `tokenHash`, `expiresAt`, `createdAt`, `deviceHint`
- `authService.py` issues and rotates refresh tokens via JWT signing + Redis blacklist

**What is missing:**
- `refreshTokenRepository.py` — **does not exist**. No code stores or looks up token hashes in `tb_8`. The table is defined but unused.
- Revocation currently works only through the Redis JWT blacklist (`TokenBlacklist.add(jti, expiresAt)`), not through DB-level token records.

**Current flow (actual):**
```
POST /auth/refresh
  → Verify refresh token signature (JWT)
  → Check JTI not in Redis blacklist
  → Revoke old JTI in Redis (rotation)
  → Issue new access + refresh tokens
  (tb_8 is never consulted)
```

**Implications:** Without DB-persisted tokens, "revoke all sessions for a user" (e.g. on password reset or account compromise) is not possible — only individual JTI revocation via logout.

**"Log out everywhere" — implemented without `tb_8`.** `POST /auth/logout-all`
writes one key per account in Redis, `revoked_before:<sha256(uid)>`, holding a
cutoff timestamp; `JwtHandler.verifyToken` refuses any token whose `iat` is
older. One write revokes every token the account holds — including the refresh
token on a lost phone that the server never sees again — and the key expires
with the longest token it could still have to refuse (7 days). The same call
disables every push device of the account (`tb_9`), because a message push
carries the first 200 characters. Audit type 6. Settings → *Log out of all
devices* in the app.

`tb_8` stays unused; a per-session list (which device, last seen) would be the
reason to wire it.

---

### 7.5 Audit Log Integration

**Status:** Implemented

**Countermeasures implemented:**

| Component | Detail |
|-----------|--------|
| Service | `auditLogsService.py` provides audit operations |
| Routes | `auditLogsRoutes.py` exposes paginated audit log queries |
| Usage | `authService.py` logs login attempts via `_logAudit()` helper |
| Encryption | Description field encrypted via `AuditLogsModel` |

**Logged events:**

| Type | Service | Event |
|------|---------|-------|
| 1 | `authService` | Successful login |
| 2 | `authService` | Failed login (user not found, blocked, banned, deleted) |
| 5 | `userService` | Account status changed |
| 6 | `authService` | Token revocation on logout |
| 7 | `streakService` | Streak reset |
| 8 | `streakService` | Badge granted |
| 10 | `reportService` | User reported another user · report resolved |
| 11 | `reportService` | Moderator read the evidence behind a report |
| 12 | `noticeService` | Warning or suspension notice sent to a user |
| 13 / 14 | `consentService` | Consent given / health-data consent withdrawn |
| 15 | `exportService` | Data export downloaded |
| 16 | `adminService` | Admin board opened |
| 17 / 18 | `postService` | Post or comment removed / restored by a moderator |
| 19 / 20 | `adminGrantService` | Administrator promoted / demoted by an official account |
| 21 / 22 | `friendshipService` | User blocked / unblocked |

**Pending:**
- [x] `core/auditTypes.AuditType` names every type; a unit test pins the values
- [x] Blocks and unblocks are audited (21 / 22). Requests, accepts, removals, chats and messages deliberately are not: they are ordinary social activity, and an audit trail of who talks to whom in a recovery app is a liability, not a control

**Where implemented:** `auditLogsService.py`, `auditLogsRoutes.py`, `auditLogsRepository.py`, `authService.py`, `userService.py`, `streakService.py`, `reportService.py`

---

## 8. Infrastructure & Configuration Risks

### 8.1 Information Leakage via Error Messages

**What it is:** Internal implementation details (file paths, line numbers, class names) leak to API clients through error responses.

**Current issue in `src/infrastructure/database/repositories/*.py`:**

```python
# This is the current pattern in every repository's except block:
raise NoHarmException(
    status_code=500,
    message=f'{type(e).__name__}: {e} in line {sys.exc_info()[-1].tb_lineno} '
            f'in file {sys.exc_info()[-1].tb_frame.f_code.co_filename}'
)
```

This exposes the server's file system layout and internal class names to any client that triggers a 500 error — extremely useful to an attacker performing reconnaissance.

**Bugs found via unit tests (now fixed):**

- ~~`messageRepository.update()` — the `except` block silently returns `None` on non-`NoHarmException` DB errors instead of raising a 500, masking failures entirely.~~ **Fixed.**
- ~~`auditLogsRepository.findByType()` — the method parameter was named `type`, shadowing Python's built-in. On DB error, the handler raised `TypeError: 'int' object is not callable`.~~ **Fixed** — parameter renamed to `logType`.

Since then repositories use `excLocation()`, which still puts the file and line
into the exception message — but that message only reaches a client in `dev`.

**Implemented countermeasures:**
- ✅ Every 5xx is logged server-side with its traceback (`logger.exception`) and recorded, encrypted, in `tb_14` by `ErrorLogService` — the admin board's Errors tab
- ✅ `main.py` exception handler returns generic `{"errorCode": "INTERNAL_ERROR", "message": "An internal server error occurred."}` for all 5xx responses in `staging` and `production` — traceback never reaches the client
- ✅ Catch-all `@app.exception_handler(Exception)` added — unhandled exceptions also return the generic 500 in non-dev environments; full traceback included only in `development`

**Pending countermeasures:**
- [ ] Nothing pages anyone on a new fault: the board shows it, and an admin with the app open gets a socket alert. A closed app hears nothing (see `operations.md`)

**Where to implement:** logging setup, `main.py` (logger integration)

---

### 8.2 Rate Limit State Loss on Restart — resolved

**What it was:** all rate limit state (`IpRateLimiter`, `LoginRateLimiter`)
lived in Python dictionaries. A restart, a worker crash or a deploy instantly
cleared every IP block and every login lockout — and under a serverless model,
where the instance dies on its own, waiting for the reset was trivial.

**Current state:** both limiters are Redis-backed, with TTLs on the keys
(`rateLimiter.py`), and `slowapi` uses the same Redis as its storage
(`limiter.py`). The state survives a container restart and is shared across
instances. `limiter.py` degrades to in-memory counting if Redis is down at
boot — a limiter that cannot reach its store must not take the API down with
it, but in that mode the ceilings apply per instance again.

**What is left depending on infra:**
- [x] Redis survives a restart: the live container runs with `--appendonly`
      on a named volume (`compose.host.yaml`). Losing the volume itself still
      un-revokes every blacklisted token; ElastiCache would be the answer on
      the ECS path.
- [x] The in-memory fallback is reported: at startup it is recorded as a
      fault (admin board → Errors) and pushed as an alert to any admin with
      the app open. It lasts until the process restarts.

**Where to implement:** `rateLimiter.py`, `limiter.py`, Redis infra

---

### 8.3 Missing Request Body Size Limit

**What it is:** Without a maximum body size, an attacker can send a gigabyte-sized JSON payload to any endpoint, causing memory exhaustion or a slow-upload DoS.

**In place:** nginx refuses REST bodies over 64 KB and socket bodies over 1 MB, and uvicorn is reachable only through nginx.

**Pending countermeasures:**
- [ ] For file upload endpoints (profile picture): validate content type and enforce a stricter limit (e.g. 5 MB) at the route level using `UploadFile` with explicit size checks

**Where to implement:** `run.py` (Uvicorn config), Nginx config

---

### 8.4 Encryption Key Compromise & Rotation

**What it is:** A single `DATABASE_ENCRYPTION_KEY` encrypts every sensitive column across all tables. If this key is ever exposed (leaked secret, compromised environment), an attacker with a database dump can decrypt everything — all usernames, emails, and messages retroactively.

**Current risk:** The column key is `DATABASE_ENCRYPTION_KEY`, kept in `prod.env` on the instance alongside the database password. A single secret file compromise exposes both.

**In place:** `rotate-encryption-key` (`src/jobs/rotateEncryptionKey.py`)
re-encrypts every `StringEncryptedType` column from `DATABASE_ENCRYPTION_KEY_OLD`
to `DATABASE_ENCRYPTION_KEY`, found from the models' metadata. It is resumable
(values already under the new key are skipped), refuses to write a table with
a value under neither key, and has a `--dry-run`. It needs a short maintenance
window — runbook in `operations.md`.

**Pending countermeasures:**
- [ ] Rotation without downtime would need the app to read with two keys at once (a key version on each value, or a decrypt fallback)
- [ ] Separate the encryption key from the database credentials — store them in different secret sources or use a secrets manager (e.g. Google Secret Manager, AWS Secrets Manager, Doppler)
- [ ] Derive per-table or per-column subkeys from the master key using HKDF — limits blast radius if one subkey is compromised


**Where to implement:** `encryption.py`, `config.py`, infrastructure

---

### 8.5 Debug Mode & Stack Traces in Production

**What it is:** `DEBUG = false` is set in `staging` and `production` in `.secrets.toml`, but `main.py` passes `debug=config.DEBUG` directly to FastAPI. If `DEBUG` is ever accidentally set to `true` in production, FastAPI will return full Python tracebacks in HTTP responses.

**Pending countermeasures:**
- [x] `Config` refuses to start with `DEBUG=true` unless `EXEC_MODE` is `dev` — this matters because Starlette's `ServerErrorMiddleware` checks `debug` *before* the installed handler, so `DEBUG=true` would serve a full traceback despite the catch-all. `run.py` only enables `reload` in dev as well
- [x] The custom handlers decide on `EXEC_MODE` (`_IS_DEV`), not on `DEBUG`

```python
# In main.py or config.py startup
if config.DEBUG and config.EXEC_MODE in ("prod", "staging"):
    raise RuntimeError("DEBUG must be false in non-development environments")
```

**Where to implement:** `main.py`, `config.py`

---

### 8.6 Host Header Injection

**What it is:** An attacker sends a forged `Host` header (e.g. `Host: evil.com`). If the application uses `request.base_url` or `request.headers["host"]` to build URLs (e.g. in password reset emails), the generated link points to the attacker's domain.

**In place:** no code builds a URL from `Host`. With `PUBLIC_HOSTNAMES` set
(`prod.env`), nginx closes the connection (444) on any other Host on :443 and
refuses to redirect one from :80 — generated by `entrypoint.sh` into
`$hostAllowed`. Unset keeps answering every Host. Only `TLS_MODE=container`
enforces it; behind an ALB that belongs in the listener rules.

**Rule:** if a URL ever has to be built server-side, take the host from config,
never from the request.

**Where to implement:** `config.py`, any future email service, Nginx config

---

### 8.7 File Upload Security (Planned Feature)

**What it is:** The storage service is planned but not yet built. File uploads are a common attack surface: malicious file types, oversized files, path traversal, and malware distribution.

**Pending countermeasures (to be implemented before launch):**
- [ ] Validate MIME type by reading the file's magic bytes — never trust the `Content-Type` header or the file extension alone
- [ ] Restrict accepted types to a whitelist: `image/jpeg`, `image/png`, `image/webp`
- [ ] Enforce a maximum file size (e.g. 5 MB) at the route level, before uploading to GCS
- [ ] Rename uploaded files to a UUID — never use the original filename
- [ ] Store files in a private GCS bucket; serve them via a signed URL with a short TTL rather than a public URL
- [ ] Do not serve uploaded files from the same domain as the API — use a separate origin or CDN to prevent MIME-type sniffing attacks

**Where to implement:** `storageService.py`, `userRoutes.py`

---

## 9. Supply Chain & Dependency Risks

### 9.1 Outdated or Vulnerable Dependencies

**What it is:** A vulnerability in a third-party package (e.g. a CVE in `cryptography`, `PyJWT`, or `FastAPI`) can compromise the entire application, regardless of how well the application code is written.

**Current state:** Dependencies are pinned to specific versions in `requirements.txt`, which prevents unexpected breaking changes, but also means security patches are not applied automatically.

**In place:** `.github/workflows/security.yml` runs `pip-audit --strict` on
every push to `main`, every pull request and every Monday — independently of
the deploy workflow, so it keeps running while that one is manual.

**Pending countermeasures:**

- [x] Dependabot (`.github/dependabot.yml` in both repos): weekly pip/npm, monthly actions and base images
- [ ] Review and update pinned versions at least monthly; prioritise security releases immediately
- [x] Test tooling moved to `requirements-dev.txt`; the image installs `requirements.txt` only
- [x] The front end runs `npm audit` in its own `security.yml` — production dependencies fail the build. Both audits are clean as of 2026-10-01

**Where to implement:** `.github/workflows/`, `requirements.txt`

---

### 9.2 Secrets in Version Control

**What it is:** `.secrets.toml` contains the database password, encryption key, and JWT secrets. If this file is ever committed to Git (even once, even on a private repository), the secrets are permanently compromised — Git history retains all commits.

**Current state:** `.gitignore` explicitly ignores `.secrets.toml` and `.env` / `.env.local`.

**Countermeasures implemented:**
- `.secrets.toml`, `.env`, `.env.local` all listed in `.gitignore`

**Pending countermeasures:**
- [x] Verified: `git log --all -- .secrets.toml docker/prod.env` is empty — neither file was ever committed, and both are in `.gitignore`
- [x] gitleaks: a pre-commit hook (`.pre-commit-config.yaml`, opt-in with `pre-commit install`) and a CI job over the whole history in both repos. The full history of both was scanned on 2026-10-01: nothing but the fake keys in `tests/conftest.py`, listed in `.gitleaksignore`
- [ ] In production the secrets come from environment variables
      (`docker/prod.env` or the ECS task definition); `.secrets.toml` is in
      `.dockerignore` and never enters the image. The remaining step is moving
      them off the on-disk file into AWS Secrets Manager, injected into the task
      definition

**Where to implement:** CI pre-commit hooks

---

## 10. Implementation Status

### Implemented ✅

| Layer | Control |
|-------|---------|
| Transport | Security headers (CSP, HSTS, X-Frame-Options, etc.) |
| Transport | CORS origin whitelist |
| Authentication | JWT access + refresh tokens with unique JTI |
| Authentication | Persistent JWT blacklist (Redis `SETEX` + TTL auto-expiry, SHA-256 hashed JTIs) |
| Authentication | Refresh token rotation — old token revoked on every `/refresh` call |
| Authentication | Per-IP rate limiting (240 req/min, escalating 60–900 s block) — global middleware, Redis |
| Authentication | Per-UID login rate limiting (5 attempts / 15 min, 30-min lockout) |
| Authentication | Per-route rate limits via `slowapi` — stricter ceilings on auth and mutation endpoints |
| Authentication | Generic "Invalid credentials" (401) for user-not-found — no UID enumeration |
| Authentication | Generic 409 on registration — no enumeration of conflicting field (email vs username) |
| Authentication | Refresh token revocation via Redis JTI blacklist (TTL-based auto-expiry) |
| WebSocket | JWT authentication on connection |
| Data at rest | AES-GCM column encryption for sensitive columns |
| Data at rest | Keyed (HMAC-SHA256) blind index for encrypted field lookups |
| Data at rest | No passwords stored — identity is Firebase's |
| Data at rest | PostgreSQL Row Level Security (RLS) policies |
| Authorization | Service-layer ownership checks on all mutating/read operations |
| Input validation | Pydantic schemas on all routes |
| Input sanitisation | HTML stripping via `bleach` |
| Error handling | Centralised `NoHarmException` — no stack traces leaked to clients |
| Configuration | `.secrets.toml` excluded from version control via `.gitignore` |
| Audit | Login success/failure, token revocation, status changes, streak resets logged |
| API | Generic pagination system with `PaginatedResponse[T]` |
| API | Pagination respects RLS policies — `total` reflects filtered count |

### Pagination with RLS

When paginating with `getDbWithRLS`, the `total` count reflects only rows the user can see per RLS policies:

| Table | Policy | Effect on Pagination |
|-------|--------|---------------------|
| `tb_0` (users) | `tb_0_select_any` | **No effect** — every user row is readable; search needs it |
| `tb_1` (streaks) | `tb_1_owner` | Counts the user's streaks only |
| `tb_2` (friendships) | `tb_2_participant` | Counts where the user is sender or receiver |
| `tb_3` (chats) | `tb_3_participant` | Counts the user's conversations |
| `tb_4` (messages) | `tb_4_select_participant` | Counts messages in the user's chats — both sides, not only their own |
| `tb_5` (badges) | none | Global catalogue, no RLS |
| `tb_6` (user_badges) | `tb_6_owner` | Counts the user's earned badges |
| `tb_7` (audit_logs) | `tb_7_select_own` | Counts entries whose catalyst is the user |
| `tb_10` (reports) | `tb_10_select_own` | Counts reports the user filed — never reports filed about them |
| `tb_11` (report evidence) | `tb_11_select_admin` | Nothing: readable only by a context-free (admin) session |
| `tb_12` (moderation notices) | `tb_12_select_own` | Counts the notices sent to the user themselves |
| `tb_13` (consent records) | owner | Counts the user's own consent rows |
| `tb_14` (error log), `tb_15` (host access) | `*_admin_all` | Nothing: only a context-free session sees them |
| `tb_16` / `tb_17` / `tb_18` (posts, comments, likes) | SELECT open | **No effect** — visibility is `PostService`'s SQL, not RLS |
| `tb_19` (admin grants) | `tb_19_select_all` | **No effect** — the mark is public anyway |

Policies read `app_current_user_id()`, a helper over
`current_setting('app.current_user_id', true)` created by the same migration.

---

### Unimplementable Rules (Require Infrastructure Changes)

Rules requiring changes outside routes/services (new tables, models, external services):

| Rule | Requirement | Why Blocked |
|------|-------------|-------------|
| 1.1 — Email Verification | Send verification email, middleware guard for `status=pending` | No email service exists — Firebase sends email; would need one plus a token table |
| ~~7.2 — Badge Milestones~~ | Grant badges at streak milestones | Unblocked — migration `20260831_01` seeds `tb_5` |
| 8.1 — Password/Email Change Audit | Log type=3 (password), type=4 (email) changes | Auth delegated to Firebase; no backend endpoints to instrument |

---

## 11. Business Rules Reference

### 11.1 Users
- Username: 3-50 chars, `^[a-zA-Z0-9_-]+$`, globally unique
- Email: valid RFC-5321, globally unique, error messages must not reveal which field duplicated
- No password: identity is a Firebase ID token (Google sign-in); nothing password-shaped is stored
- On registration: `status = pending` (if email unverified) or `enabled`
- Profile updates: only `username`, `profilePicture` allowed; `status` changes via admin only

### 11.2 Authentication & Tokens
- Access token: 15 min, `JWT_SECRET_KEY`, claims: `sub`, `type:access`, `exp`, `iat`, `jti`
- Refresh token: 7 days, `JWT_REFRESH_SECRET_KEY`, not stored — revoked through the Redis blacklist (`tb_8` is unused, §7.4)
- Login rate limit: 5 attempts / 15 min, 30-min lockout
- IP rate limit: 240 req / 60 sec, 60 s block doubling up to 900 s

### 11.3 Friendships
- Cannot send request to self
- Cannot send if any active friendship exists (unless `deleted`)
- Only receiver may accept/reject
- Either may block — a friend or a stranger (`POST /users/{id}/block`); **only the one who blocked may unblock** (`cl_2g`). Blocked users cannot send requests or view profiles
- Chat pre-condition: must be `accepted` friends — except an official account, which may open a chat with anyone

### 11.4 Chats
- Creation requires `accepted` friendship
- No duplicate active chats between same users
- Either participant may end (sets `endedAt`, `status=disabled`)

### 11.5 Messages
- Only to `enabled` chats
- Content sanitized with `Sanitizer.cleanHtml()`
- `markAsRead`: sets `status=read`, `recivedAt`

### 11.6 Streaks
- One active streak per user
- Fields: `start_at` (set on creation), `end_at` (null until relapse), `last_checkin` (updated on each check-in)
- Duration = `end_at - start_at` for closed streaks; `now - start_at` for active streaks
- Streaks reset only on explicit relapse (`POST /streaks/end`) — no auto-expiry on inactivity
- On reset: sets `end_at`, creates new streak, updates `isRecord` if longest

### 11.7 Badges
- Granted by `StreakService._checkAndGrantBadges()` on start, check-in, relapse and every `GET /streaks/current` (clean days accrue with time, so a read is the accrual trigger)
- One per user only; `givenAt` set on grant

### 11.8 Audit Logs
| Action | Type Code |
|--------|-----------|
| Successful login | 1 |
| Failed login | 2 |
| Password change | 3 |
| Email change | 4 |
| Account status change | 5 |
| Token revocation | 6 |
| Streak reset | 7 |
| Badge granted | 8 |
| Admin action | 9 |
| User reported / report resolved | 10 |
| Moderator read report evidence | 11 |
| Warning or suspension notice sent | 12 |
| Consent given / health consent withdrawn | 13 / 14 |
| Data export | 15 |
| Admin board read | 16 |
| Content removed / restored | 17 / 18 |
| Administrator promoted / demoted | 19 / 20 |
| User blocked / unblocked | 21 / 22 |

### 11.8.1 Reports

- A report names another account: `POST /reports/{userId}`, one of six reasons,
  optional free text capped at 1000 characters (sanitised, then encrypted at
  rest in `tb_10.cl_10e`).
- Cannot report yourself; cannot report an account that does not exist or is
  deleted; one **open** report per (reporter, reported) pair — a second before
  the first is reviewed is 409 `REPORT_ALREADY_OPEN` — unless the new report
  names a post or comment, in which case it is appended to the open one (D8,
  200 `appended: true`). Rate limited to 5/minute per IP, plus the per-account
  ceilings in the root `CLAUDE.md`, "Report abuse ceilings".
- **Only the reporter can read a report.** `GET /reports/mine` returns their own;
  the reported user has no way to learn a report exists or who filed it, in the
  service and in the `tb_10_select_own` policy both.
- Reporting is silent: no socket event, no push, no change to the friendship.
  Blocking stays the separate, visible action the reporter can also take.
- Moderation (`GET /reports`, `GET /reports/{id}`,
  `PUT /reports/{id}/resolve/{status}`) is behind `getAdminUser` — the
  `ADMIN_USER_IDS` allowlist, official accounts and `tb_19` grants — and runs on `getDb`, because the table's policies
  are reporter-scoped. Resolving never changes an account: banning is still
  `PUT /users/{id}/status/{status}`.
- Reports are append-only from the application: `tb_10` has an UPDATE policy
  that only a context-free session satisfies, and no DELETE policy at all.
  Purging **either** account keeps the record: `cl_10b` (reporter) and `cl_10c`
  (reported) are both ON DELETE SET NULL, and `cl_10g`/`cl_10h` hold the
  reported uid and username copied at filing time. Deleting an account is
  therefore not a way to unfile a complaint, nor to erase the complaints about
  you — which it was while `cl_10c` cascaded.

### 11.8.2 Report evidence (`tb_11`)

- A report carries a copy of what it is about, captured when it is filed: the
  reported profile as it was, and the last 20 messages of the conversation when
  the request named one (`ReportRequest.chatId`).
- **The request body carries an id, never content.** Message bodies are read out
  of `tb_4` by the server, under the reporter's own RLS context, so a reporter
  can only ever capture a conversation they are in — and cannot attribute
  invented lines to the account they are reporting. `extra="forbid"` refuses any
  field that would carry text.
- Content is encrypted at rest like a message body (`cl_11f`) and carries a
  keyed hash of the plaintext (`cl_11g`, `Encryption.hash`), so a row altered
  after capture no longer matches its own hash.
- **Admin-only to read**: `GET /reports/{id}/evidence`, behind `getAdminUser`,
  and every call writes an audit entry of type 11. Neither the reported user nor
  the reporter can read the table — `tb_11_select_admin` passes only for a
  context-free session. There is no UPDATE policy at all, and DELETE is
  context-free only.
- Snapshots outlive the accounts they name: `cl_11d`/`cl_11e` are plain strings
  with no foreign key, so evidence survives the purge of the account it is
  about, which is when it matters most.
- Retention: `purge-evidence` (cron) deletes evidence whose report has been
  resolved for `REPORT_EVIDENCE_RETENTION_DAYS` (default 180). The report itself
  is permanent; the copied prose is not. Open reports are never swept.

### 11.8.3 Suspensions and the review lock

- `PUT /users/{id}/suspend` (admin) bans an account until a date —
  `{days: null}` bans it permanently, spelled out so a missing field cannot
  mean "for ever". `days` is capped at `MAX_SUSPENSION_DAYS` (365).
- A suspension is `status = banned` (9) plus `tb_0.cl_0g`, so every existing
  refusal — login, register, reactivate, refresh, and the status check on every
  authenticated request — applies to it with no new branch.
- It **lifts itself** at the first sign-in past the date
  (`AuthService._liftExpiredSuspension`). No scheduled job: an account nobody
  is signing in to needs no unbanning, and one more cron is one more thing that
  can silently stop.
- The refusal names the date: 403 `ACCOUNT_SUSPENDED` with
  `details.suspendedUntil`. A permanent ban stays plain `ACCOUNT_BANNED`.
- Lifting a ban through `PUT /users/{id}/status/{status}` clears the date with
  it. A stale `cl_0g` would make a later permanent ban expire on its own.
- **The review lock** (`tb_10.cl_10i`/`cl_10j`, `POST`/`DELETE /reports/{id}/claim`)
  stops two moderators acting on one report: a live claim by someone else is
  409 on claim, release and resolve. It expires after `REPORT_LOCK_MINUTES`
  (30) so a closed tab cannot park a report for ever. `locked_by` reaches the
  admin queue only — `GET /reports/mine` never names the moderator reading a
  report.
- Resolving a report never changes an account, and suspending never closes a
  report. Two decisions, two calls, two audit entries (type 10 and type 5).

### 11.8.4 Moderation notices (`tb_12`)

- `POST /users/{id}/warn` (admin) sends a warning: the user is told, and
  **nothing about the account changes**. `PUT /users/{id}/suspend` writes a
  suspension notice alongside the ban.
- `GET /notices/mine` and `POST /notices/{id}/ack` are the recipient's, and
  only theirs — another user's notice answers 404, and `tb_12_select_own` says
  the same at the database.
- A notice carries the **conduct code**, optionally the moderator's words
  (sanitised, encrypted at rest), and never the reporter's identity or the
  moderator's uid. The response model omits both.
- `self_harm` is refused as a warning reason (400 `NOT_A_WARNING`).
- Only a context-free session can insert one (`tb_12_insert_admin`), so a
  notice cannot be self-issued; there is no DELETE policy, so what moderation
  said is not something it gets to unsay.
- Audit type 12 records who sent what to whom, naming the conduct and never the
  free text.

### 11.9 Cross-Cutting Rules
- **Soft Delete**: All entities use `status=deleted`. User accounts are the one
  exception to "never hard delete": a soft-deleted account is destroyed for real
  by the `purge-accounts` job once `ACCOUNT_DELETION_GRACE_DAYS` (default 30)
  have passed since `tb_0.cl_0f`. See 11.10.
- **Ownership Checks**: Service layer verifies ownership before repository calls
- **Input Sanitization**: All free-text passes through `Sanitizer.cleanHtml()`
- **User ID**: `tb_0.cl_0a` uses Firebase UID (opaque string). All other PKs (`tb_1`–`tb_10`) are UUID v4. No sequential integers anywhere.
- **Status Codes**: `disabled=0`, `enabled=1`, `deleted=2`, `blocked=3`, `pending=4`, `accepted=5`, `ignored=6`, `unread=7`, `read=8`, `banned=9`. A timed suspension is `banned` plus `tb_0.cl_0g`, not a code of its own, and "a report is in review" is `tb_10.cl_10i`/`cl_10j`, not a code either — `STATUS_CODES` is shared with the front end, and neither condition is one a client ever sees.
- **Timestamps are naive UTC**: `datetime.now(timezone.utc).replace(tzinfo=None)`, matching what the columns hold. A local-time write into `deleted_at`, `banned_until` or a report lock is a comparison that silently goes wrong by the host's offset.

### 11.9.1 Reads are checked in the service, not only by RLS

`GET /messages/chat/{chatId}` and `/messages/chat/{chatId}/unread` took the
authenticated user id and never used it: `MessageService.getByChatId` went
straight to the repository with the chat id. The `tb_4` policy was therefore the
**only** control on them, which contradicts the posture stated for RLS
everywhere else in this document — defence in depth, not the access-control
layer. Chat ids are not secret (they appear in every chat-list response), so any
context where the policy does not apply — a role with BYPASSRLS or superuser, a
session with no RLS context, a future migration that drops the policy — turned
those two endpoints into a way to read any conversation.

Both now call `_assertParticipant` first and answer 403 `FORBIDDEN`, the same
check `markAsRead` and `markAllAsRead` already performed. Covered in
`tests/unit/services/test_messageService.py` and
`tests/integration/test_message.py::TestMessageRLS`.

### 11.10 Account Deletion and Reactivation

Deleting an account is a soft delete plus a disclosed clock, not a status flip
that lasts forever.

| Stage | State | What the API answers |
|-------|-------|----------------------|
| `DELETE /users/me` | `status=deleted`, `cl_0f = now` | account invisible everywhere; access tokens rejected by `getCurrentUser`, refresh rejected by `AuthService.refresh` |
| inside the window | unchanged | login/register → 403 `ACCOUNT_PENDING_DELETION` + `details.deletionScheduledAt`; `POST /auth/reactivate` restores it |
| window closed | unchanged, awaiting purge | login/register/reactivate → 403 `ACCOUNT_DELETED`, "Account not found." |
| purged | row gone | 401, as for any UID that was never registered |

Three properties are deliberate:

- **The window is disclosed, not hidden.** The delete confirmation names the
  number of days and says signing in restores everything. Retention that users
  are told about is ordinary; retention they discover is the thing they object
  to, and GDPR Art. 17 reads the same way — a stated execution window is lawful,
  silent retention is not.
- **Reactivation is explicit.** `POST /auth/reactivate` exists rather than
  login restoring the account on its own. Restoring puts a profile, a friend
  list and a streak history back in front of other people; in a recovery app,
  where deleting is often a response to a relapse, doing that because someone
  tapped "sign in" would be a disclosure they never agreed to.
- **A ban outranks a deletion.** Banned is checked before the deletion branch in
  login, register and reactivate, so deleting an account is not a way to shed a
  ban and come back.

**The purge is the whole guarantee.** `docker compose run --rm app purge-accounts`
(cron on the live host, see `docs/operations.md`) is the only code path that hard
deletes a user. If it is not scheduled, the promise on the delete screen is
never kept and nothing anywhere reports that — a deleted account past its window
looks identical from outside whether the row still exists or not.

The cascade that makes it possible is migration `20260901_01`: every FK into
`tb_0` gained `ON DELETE CASCADE`, except `tb_7.cl_7c` (audit logs), which gained
`ON DELETE SET NULL` so the record that the deletion happened outlives the
account. One consequence to be aware of: both halves of a 1-on-1 chat live in one
`tb_3` row, so purging an account also removes the other participant's copy of
that conversation.

**Admin surface.** `PUT /users/{id}/status/{status}` can set any account to any
status — it is how a ban is applied, lifted, or a deletion undone. It sits
behind `getAdminUser`: the `ADMIN_USER_IDS` allowlist, the official accounts, and
the accounts an official account promoted (`tb_19`) — all empty by default. Before that dependency existed the route was authenticated-only,
which let any signed-in user unban themselves or ban anyone else, and made every
banned-account check elsewhere unenforceable.

---

## 12. RLS Setup and Usage

### 12.1 Overview
RLS ensures queries only return rows the authenticated user can see. Enforced at database level — defense-in-depth even if application code vulnerable.

### 12.2 How It Works
1. JWT validated, Firebase UID extracted as `userId` (string)
2. `getDbWithRLS` calls `RLSContext.setUserId`, which records the user on
   `Session.info` and stamps it onto the current transaction with
   `set_config('app.current_user_id', userId, true)`
3. An `after_begin` listener re-stamps it onto every later transaction the
   session opens. Without that the context would be gone after the first
   `commit()` a repository makes, and a Session releases its connection to the
   pool at the end of each transaction, so session-scoped settings do not
   survive either
4. Queries then filter through the policies of migration `20260831_02`

**If no user is set, policies pass — this is fail-open, deliberately.** Several
paths legitimately touch rows belonging to other users and none of them has a
context to set: `/auth/*` runs on `getDb`, `fcmService.sendPushToUser` reads the
recipient's device tokens from its own session, and `userBadgesRepository` takes
its session in the constructor rather than from the request. Fail-closed would
break all three as empty results rather than errors. Setting the variable is
what *turns RLS on* for a request; RLS is a floor under the service layer's own
ownership checks, not a replacement for them.

A role with `BYPASSRLS` or superuser ignores every policy. `FORCE ROW LEVEL
SECURITY` covers the table owner, not that attribute — the application should
connect as a `NOSUPERUSER`, `NOBYPASSRLS` role holding only DML grants.

In the live deployment it does: `docker/postgres-init/10-app-role.sh` creates
`noharm_app` when the Postgres volume is first initialised, and the app connects
as it. `ALTER DEFAULT PRIVILEGES` is part of that script because a later
migration creating a table would otherwise produce one the app cannot read —
and `pg_restore` does not recreate it, which is why `restore-db.sh` re-runs the
grants. See [`operations.md`](operations.md).

### 12.3 Usage in Routes

**Recommended**: Use `getDbWithRLS` for authenticated endpoints:
```python
@router.get("/streaks")
def getMyStreaks(db: Session = Depends(getDbWithRLS)):
    # RLS automatically filters to current user's rows
    return db.query(StreakModel).all()
```

**Public endpoints**: Use `getDb` without RLS:
```python
@router.get("/public/health")
def healthCheck(db: Session = Depends(getDb)):
    pass  # No RLS context for public endpoints
```

### 12.4 Bypassing RLS (Admin Operations)
```python
# Use getDb (without RLS) and apply filters manually
@router.get("/admin/users")
def adminGetAllUsers(db: Session = Depends(getDb)):
    return db.query(UserModel).all()
```

### 12.5 Testing RLS
`tests/integration/test_rls.py` asserts the policies against the tables
directly, rather than through the API — the `TestXxxRLS` classes elsewhere in
that suite would still pass with every policy dropped, because what they check
is that the services scope their own queries.

It **skips itself** when the connecting role bypasses RLS, which the superuser
of a stock Postgres image does. To actually run it, point it at a role that
does not:

```sql
CREATE ROLE noharm_app LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO noharm_app;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public TO noharm_app;
```

```bash
RLS_TEST_DATABASE_URL=postgresql://noharm_app:...@localhost/noharm_test \
TEST_DATABASE_URL=postgresql://noharm_app:...@localhost/noharm_test \
  pytest tests/integration/test_rls.py -v
```

Note the absence of a "without context returns nothing" assertion: with no
context the policies pass, and `test_no_context_sees_both` asserts exactly
that.

### 12.6 Troubleshooting
| Issue | Cause | Fix |
|-------|-------|-----|
| `new row violates row-level security policy` | A write naming another user — an INSERT whose owner column is not the session's user | Check what the service is writing; this is the policy doing its job |
| An UPDATE or DELETE matches 0 rows | The row is invisible to this context, so there is nothing to update. Silent by design — Postgres does not error on a filtered-out row | Confirm the context is the row's owner |
| Empty results everywhere | Wrong user in the context | `SELECT app_current_user_id()` on the same session |
| Policies appear to do nothing | The connecting role has `BYPASSRLS` or is a superuser | `SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user` |
| Nothing is filtered on `/auth/*` or in push | No context set — fail-open, by design (§12.2) | Expected |

Indexes for the policy predicates (`cl_1b`, `cl_2b`, `cl_2c`, `cl_3b`, `cl_3c`,
`cl_4b`, `cl_6b`, `cl_7c`, `cl_9b`) are created by migration `20260831_02`. They
matter more than they look: a policy adds its predicate to *every* query against
the table, so without them each read is a sequential scan.

---

### Recently Fixed ✅

| Control | Section | Location |
|---------|---------|----------|
| Stack traces never reach clients in staging/production — generic 500 returned | §8.1 | `main.py` |
| Catch-all `Exception` handler added — unhandled exceptions return generic 500 | §8.1 | `main.py` |
| `messageRepository.update()` — now raises `NoHarmException(500)` on DB error | §8.1 | `messageRepository.py` |
| `auditLogsRepository.findByType()` — param renamed `logType`, no longer shadows `type` builtin | §8.1 | `auditLogsRepository.py` |
| `userService.getPublicProfile()` — non-404 from `findByUsers` now re-raises correctly | §7.1 | `userService.py` |
| `authService.register()` — every uniqueness lookup re-raises non-404 errors | §7.1 | `authService.py` |
| `GET /users`, `GET /users/{id}` and the status route no longer return e-mail, status or birth date | §5.1 | `userSchemas.py`, `userRoutes.py` |
| Socket messages capped at 2000 characters like REST | §6.1 | `messageService.py` |
| `pip-audit` in CI, weekly and on every push | §9.1 | `.github/workflows/security.yml` |
| Server-side traceback logging, encrypted fault log | §8.1 | `main.py`, `errorLogService.py` |
| `DEBUG=true` refused outside dev; reload only in dev | §8.5 | `config.py`, `run.py` |
| User search by username only — no e-mail membership oracle | §7.1 | `userRepository.py` |
| "Log out everywhere": per-account token cutoff + push devices disabled | §7.4 | `jwtHandler.py`, `tokenBlacklist.py`, `authService.py` |
| `extra="forbid"` on every request body | §2.3 | schemas, route bodies |
| nginx slow-client timeouts, 64 KB body cap, `PUBLIC_HOSTNAMES` | §4.2, §8.3, §8.6 | `nginx.conf`, `server.tls.conf`, `entrypoint.sh` |
| Column key rotation job + runbook | §8.4 | `jobs/rotateEncryptionKey.py`, `operations.md` |
| Degraded rate limiter reported on the board and to admins | §8.2 | `limiter.py`, `main.py` |
| WebSocket cap evicts the oldest socket; self-healing | §6.1 | `websocket/rateLimiter.py` |
| `AuditType` enum; block/unblock audited | §7.5 | `core/auditTypes.py` |
| `requirements-dev.txt`, Dependabot, gitleaks (hook + CI); npm audit clean | §9 | both repos |

### Pending ⬜

Validated against the code on 2026-10-02. The three findings at the top come
from the generated route reference (`docs/API.md`), which shows the gate each
route actually declares.

| Priority | Control | Why it is still open | Section |
|----------|---------|----------------------|---------|
| **High** | Make `POST /logs` server-only (remove it, or `getAdminUser`) | Any signed-in account can write audit entries with any type and any `catalyst_id` — the audit trail can be forged in someone else's name | §7.5 |
| **High** | Put the badge catalogue's writes behind `getAdminUser` | `POST /badges`, `PUT /badges/update/{id}`, its status route and `DELETE /badges/{id}` accept any signed-in account, and `tb_5` has no RLS: anyone can vandalise the badges every user sees | §5.2 |
| **Medium** | Remove or gate `POST /user-badges/{userId}/{badgeId}` | An account can grant itself any badge (RLS only stops granting to others); the app never calls it — `StreakService` grants badges | §5.2 |
| **Medium** | Secrets off the instance disk | `prod.env` holds the column key next to the database password. A real fix is a secrets manager the instance reads through an IAM role — and the box deliberately has no AWS credentials today. A decision about infrastructure, not code | §8.4, §9.2 |
| **Low** | Key rotation without downtime | Rotation works (`rotate-encryption-key`) but needs a maintenance window of seconds | §8.4 |
| **Low** | Pager-grade alerting | Faults and the degraded limiter reach the admin board and any admin with the app open; nothing reaches a closed app | §8.1, §8.2 |

### Not applicable today

Kept so they are not re-added by the next audit:

| Item | Why it does not apply |
|------|----------------------|
| Constant-time login, CAPTCHA, 2FA, forgot-password (§1.2, §7.1, §7.3) | No passwords: identity is a Google-issued Firebase token |
| CSRF protections (§3.1) | No cookies — JWTs travel in the `Authorization` header |
| File upload security (§8.7) | No upload endpoint exists; profile pictures are the Google account's URL. Applies the day uploads are built |
| Email verification and email-based flows (§7.2, §8.6) | The backend sends no email |
| Burst protection (§4.1) | The per-route `slowapi` ceilings already bound bursts on every route |

---

## Dependency Reference

Security-critical packages and their purpose, as pinned in `requirements.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| `PyJWT` | 2.15.1 | JWT encoding / decoding |
| `firebase-admin` | 6.5.0 | Verifying Firebase ID tokens; FCM push |
| `SQLAlchemy-Utils` | 0.42.1 | `StringEncryptedType` — AES-GCM column encryption |
| `cryptography` | 50.0.1 | The AES-GCM primitive under the column encryption |
| `argon2-cffi` | 23.1.0 | Argon2 helpers in `encryption.py` (no password is stored today) |
| `bleach` | 6.4.0 | HTML sanitisation (XSS prevention) |
| `redis` | 5.0.1 | Blacklist, rate limits, quotas, presence |
| `slowapi` | 0.1.9 | Per-route rate limits |
| `pydantic` | 2.13.0 | Input validation and type enforcement |
| `email-validator` | 2.3.0 | Email format validation |
