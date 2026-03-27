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
| Persistent blacklist | Revoked JTIs are stored hashed (SHA-256) in a JSONL file via `TokenBlacklist` |
| Refresh token rotation | Each `/refresh` call should invalidate the old refresh token |

**Token lifecycle:**
```
Login → issue accessToken (15 min) + refreshToken (7 days)
        │
        ├─ Each request → verify accessToken → check blacklist
        │
        └─ On expiry → POST /refresh → verify refreshToken
                                      → revoke old refreshToken (blacklist)
                                      → issue new accessToken + new refreshToken

Logout → revoke accessToken + revoke refreshToken → both added to blacklist
```

**Blacklist implementation (`src/security/tokenBlacklist.py`):**

The blacklist uses `PersistentHashTable` — an append-only JSONL log. Each `add` operation costs O(1) (single file append). On startup the state is rebuilt by replaying all events. Expired entries are removed via `cleanup()`. JTIs are stored as SHA-256 hashes — plaintext JTIs are never written to disk.

---

### 1.2 Brute Force Login

**What it is:** An attacker tries thousands of password combinations until one succeeds.

**Countermeasures implemented (`src/security/rateLimiter.py`):**

`LoginRateLimiter` — per-username sliding window:

| Configuration | Value |
|---------------|-------|
| Window | 15 minutes |
| Max attempts | 5 |
| Lockout duration | 30 minutes |
| Reset on success | Yes — `onSuccess(username)` clears the attempt history |

`IpRateLimiter` — per-IP sliding window:

| Configuration | Value |
|---------------|-------|
| Window | 60 seconds |
| Max requests | 60 |
| Block duration | 60 minutes |

**Pending countermeasures:**
- [ ] Constant-time response (add `time.sleep(0.1)` regardless of success/failure to prevent timing attacks)
- [ ] CAPTCHA after 3 consecutive failures
- [ ] Generic error messages that do not reveal whether the username exists

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

**Pending countermeasures:**
- [ ] Apply `Sanitizer.cleanHtml()` consistently in all schemas that accept free-text fields (message content, display names, etc.)

---

### 2.3 Mass Assignment

**What it is:** An attacker includes extra fields in a request body (e.g. `"isAdmin": true`) that should not be settable by regular users.

**Countermeasures implemented:**

Pydantic schemas act as an explicit whitelist. Only fields declared in a schema can be updated. FastAPI ignores any extra fields by default.

**Pending countermeasures:**
- [ ] Add `model_config = ConfigDict(extra='forbid')` to all input schemas to actively reject unexpected fields rather than silently ignore them

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

**Countermeasures implemented (`src/security/rateLimiter.py`, `src/security/middleware.py`):**

`RateLimitMiddleware` applies `IpRateLimiter` globally on every request:
- 60 requests / 60 seconds per IP
- Excess requests → 429 with `Retry-After: 60`
- IP blocked for 60 minutes after exceeding the limit

`LoginRateLimiter` applies per-username limits on the login endpoint (see §1.2).

**Pending countermeasures:**
- [ ] Per-endpoint rate limits (e.g. stricter limits on `/auth/login`, `/auth/refresh`)
- [ ] Burst protection (e.g. max 10 requests/second before sliding window kicks in)
- [ ] Redis-backed rate limiting for multi-instance deployments (current in-memory state is not shared across workers)

---

### 4.2 Slowloris / Connection Exhaustion

**What it is:** Attacker keeps thousands of connections half-open, exhausting server threads.

**Countermeasures (infrastructure-level, pending):**
- [ ] Configure Uvicorn `timeout_keep_alive=5`, `limit_concurrency=1000`
- [ ] Nginx reverse proxy with `client_header_timeout 10s`, `client_body_timeout 10s`, `keepalive_timeout 5s`
- [ ] `client_max_body_size 1m` to reject oversized payloads early

---

## 5. Data Attacks

### 5.1 Data Exposure

**What it is:** Sensitive data leaks through API responses, logs, or error messages.

**Countermeasures implemented:**

**Field-level encryption at rest** (`src/security/encryption.py`):
- All sensitive columns (username, email, message content, timestamps) are encrypted with AES-256 (Fernet) before being written to PostgreSQL
- Obfuscated column names (`cl_0a`, `cl_0b`, ...) add an additional layer of obscurity
- Each encrypted column has a parallel `_hash` column (SHA-256) for equality queries

**Response filtering:**
- Pydantic `response_model` on every route ensures only declared fields are returned
- `passwordHash` and internal columns are never included in any response schema

**Pending countermeasures:**
- [ ] Structured log sanitisation — ensure no sensitive values appear in log output
- [ ] Add `response_model_exclude_unset=True` where appropriate to avoid leaking default values

---

### 5.2 Insecure Direct Object Reference (IDOR)

**What it is:** A user accesses another user's resources by guessing or iterating resource IDs.

**Countermeasures implemented:**
- All primary keys are **UUIDs** (v4), not sequential integers — not guessable
- `getCurrentUser` dependency injects the authenticated user's ID into every protected route

**Pending countermeasures:**
- [ ] Ownership checks in all `Service` methods — verify that the authenticated user owns the requested resource before returning or modifying it

---

## 6. WebSocket Attacks

### 6.1 WebSocket Hijacking / Unauthenticated Connections

**What it is:** An attacker connects to the WebSocket endpoint without a valid token.

**Countermeasures planned (`src/websocket/socketManager.py`):**
- [ ] Mandatory JWT authentication on every `connect` event — reject connection if token is missing or invalid
- [ ] Rate limiting on message events (max 20 messages / minute per user)
- [ ] Strict payload validation — reject messages with unexpected fields or oversized content
- [ ] Maximum 5 simultaneous connections per user — evict oldest on overflow
- [ ] CORS origin whitelist on the Socket.IO server

---

## 7. Account & Identity Attacks

### 7.1 Account Enumeration

**What it is:** An attacker probes the API to discover which email addresses are registered, building a list for targeted attacks (phishing, credential stuffing).

**How it happens:**
- `POST /auth/login` returns `"User not found"` for unknown emails and `"Invalid password"` for known ones — the attacker can tell the difference
- `POST /auth/register` returns a conflict error for duplicate emails — confirming the email is taken
- Forgot-password flows that confirm whether the email exists

**Why this matters for NoHarm:** Users are in addiction recovery. Confirming their presence on the platform to a third party is a privacy violation with real personal-safety implications.

**Pending countermeasures:**
- [ ] Unified error message for login: `"Invalid credentials"` regardless of whether the email exists or the password is wrong — both cases must return the same response body, status code, and response time
- [ ] Registration endpoint: return the same success-like response whether the email is new or already taken; send a `"you already have an account"` email to the existing address instead of leaking the conflict in the HTTP response
- [ ] Forgot-password endpoint (when built): always respond with `"If this email is registered, you will receive a reset link"` — never confirm or deny

**Where to implement:** `authRoutes.py`, `userService.py`

---

### 7.2 Missing Email Verification

**What it is:** Users register with any email address without proving they own it. This allows registering with someone else's email, polluting the account, and blocking the real owner from registering.

**Pending countermeasures:**
- [ ] On registration, set `user.status = STATUS_CODES["pending"]` and send a verification email with a signed, time-limited token
- [ ] Block access to protected endpoints until `user.status == STATUS_CODES["enabled"]`
- [ ] Verification token: sign with HMAC-SHA256 using `JWT_SECRET_KEY`, include `userId` + `exp` (24h), store hash in database to allow single-use
- [ ] Resend endpoint with its own rate limit (max 3 resends per hour per email)

**Where to implement:** `userService.py`, `authRoutes.py`, `emailService.py`

---

### 7.3 Missing Secure Password Reset

**What it is:** There is no password reset flow. A user who forgets their password has no way to recover their account.

**Attack surface if implemented insecurely:**
- Predictable reset tokens (sequential IDs, short numeric codes)
- Tokens that never expire
- Tokens that are reusable after first use
- Reset links sent over HTTP

**Pending countermeasures:**
- [ ] Generate a `secrets.token_urlsafe(32)` reset token, store its SHA-256 hash in the database with a 1-hour expiry
- [ ] Send only the plaintext token in the email — never store plaintext
- [ ] On reset: verify token hash, check expiry, delete token immediately (single-use), invalidate all existing access and refresh tokens for the user, then update the password hash
- [ ] Apply the same rate limit as login (max 3 reset requests per hour per IP and per email)

**Where to implement:** `userService.py`, `authRoutes.py`, `emailService.py`

---

### 7.4 Missing Refresh Token Persistence

**What it is:** Refresh tokens are issued but not stored in the database. This means:
- There is no way to invalidate all sessions for a user (e.g. on password change or account compromise)
- A stolen refresh token cannot be detected via reuse — if an attacker and the real user both hold valid refresh tokens, both will keep getting new access tokens indefinitely

**Pending countermeasures:**
- [ ] Store a SHA-256 hash of each refresh token in a `refreshTokens` table with `userId`, `hashedToken`, `expiresAt`, `createdAt`, `deviceHint`
- [ ] On `POST /auth/refresh`: look up the hash, verify it exists and is not expired, delete it (rotation), issue a new pair
- [ ] On password change or suspicious activity: delete all rows for `userId` — this logs out all devices
- [ ] On logout: delete only the specific row — this logs out one device without affecting others

**Where to implement:** new `refreshTokenRepository.py`, `userService.py`, `authRoutes.py`

---

### 7.5 Missing Audit Log Integration

**What it is:** The `AuditLogsModel` and `AuditLogsRepository` are fully built but never called from any service or route. Security-sensitive actions leave no trace.

**Actions that must be audited:**
- Successful and failed login attempts (with IP)
- Password change
- Email change
- Account status changes (blocked, banned)
- Token revocation
- Streak reset
- Any admin-level action

**Pending countermeasures:**
- [ ] Create an `AuditService` that wraps `AuditLogsRepository` and exposes a single `log(type, catalystId, description)` method
- [ ] Call `auditService.log()` from every service method that performs a sensitive action
- [ ] Define a `LOG_TYPES` enum (e.g. `LOGIN_SUCCESS=1`, `LOGIN_FAILURE=2`, `PASSWORD_CHANGE=3`, ...) and document it in `STATUS_CODES` style in `.secrets.toml`
- [ ] Ensure audit log entries are **never deleted** (append-only) and that the `description` field is encrypted (already supported by `AuditLogsModel`)

**Where to implement:** new `auditService.py`, all `*Service.py` files

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

**Pending countermeasures:**
- [ ] Log the full traceback server-side (to a structured logger or Sentry) but return a generic message to the client: `"An internal error occurred"` with only the `errorCode`
- [ ] Introduce a logging wrapper that captures `exc_info=True` and strips all sensitive detail from the client response
- [ ] In `main.py`, add a catch-all exception handler for unhandled `Exception` (not just `NoHarmException`) that prevents FastAPI's default detail from leaking

```python
@app.exception_handler(Exception)
async def unhandledExceptionHandler(request: Request, exc: Exception):
    logger.error("Unhandled exception", exc_info=True)
    return JSONResponse(status_code=500, content={"errorCode": "INTERNAL_ERROR", "message": "An internal error occurred"})
```

**Where to implement:** all `*Repository.py` files, `main.py`

---

### 8.2 Rate Limit State Loss on Restart

**What it is:** All rate limiter state (`IpRateLimiter`, `LoginRateLimiter`) lives in Python dictionaries in memory. A server restart, worker crash, or deployment resets every IP block and login lockout instantly.

**Attack scenario:** An attacker performs 4 failed login attempts, waits for a deploy (common on Vercel's serverless model), then continues — the lockout counter resets to 0.

**Pending countermeasures:**
- [ ] Persist rate limiter state to Redis with TTL-based keys (replaces in-memory dicts)
- [ ] On Vercel serverless: consider rate limiting at the edge (Vercel's built-in rate limiting or Upstash Redis)
- [ ] Alternatively, use a stateless approach: store a short-lived signed token in the response that encodes the attempt count — the client must echo it on the next request (works without shared state)

**Where to implement:** `rateLimiter.py`, infrastructure config

---

### 8.3 Missing Request Body Size Limit

**What it is:** Without a maximum body size, an attacker can send a gigabyte-sized JSON payload to any endpoint, causing memory exhaustion or a slow-upload DoS.

**Pending countermeasures:**
- [ ] Set `app = FastAPI(...)` with no built-in limit, but configure Uvicorn: `--limit-request-body-size 1048576` (1 MB)
- [ ] Nginx: `client_max_body_size 1m`
- [ ] For file upload endpoints (profile picture): validate content type and enforce a stricter limit (e.g. 5 MB) at the route level using `UploadFile` with explicit size checks

**Where to implement:** `run.py` (Uvicorn config), Nginx config

---

### 8.4 Encryption Key Compromise & Rotation

**What it is:** A single `ENCRYPTION_KEY` is used to encrypt every sensitive field across all tables. If this key is ever exposed (leaked secret, compromised environment), an attacker with a database dump can decrypt everything — all usernames, emails, and messages retroactively.

**Current risk:** The key is stored in `.secrets.toml` alongside the database password. A single secret file compromise exposes both.

**Pending countermeasures:**
- [ ] Key versioning: prefix encrypted values with a key version identifier (e.g. `v1:...`). When rotating, re-encrypt rows in batches using the new key while old ones are still decryptable with the old key
- [ ] Separate the encryption key from the database credentials — store them in different secret sources or use a secrets manager (e.g. Google Secret Manager, AWS Secrets Manager, Doppler)
- [ ] Derive per-table or per-column subkeys from the master key using HKDF — limits blast radius if one subkey is compromised
- [ ] Define a key rotation runbook: how to re-encrypt all rows with a new key without downtime

**Where to implement:** `encryption.py`, `config.py`, infrastructure

---

### 8.5 Debug Mode & Stack Traces in Production

**What it is:** `DEBUG = false` is set in `staging` and `production` in `.secrets.toml`, but `main.py` passes `debug=config.DEBUG` directly to FastAPI. If `DEBUG` is ever accidentally set to `true` in production, FastAPI will return full Python tracebacks in HTTP responses.

**Pending countermeasures:**
- [ ] Add a startup guard that raises a hard error if `DEBUG=true` and `EXEC_MODE` is `"prod"` or `"staging"`
- [ ] Regardless of `DEBUG`, always use the custom `noHarmExceptionHandler` and the catch-all handler (see §8.1) to prevent tracebacks from reaching clients

```python
# In main.py or config.py startup
if config.DEBUG and config.EXEC_MODE in ("prod", "staging"):
    raise RuntimeError("DEBUG must be false in non-development environments")
```

**Where to implement:** `main.py`, `config.py`

---

### 8.6 Host Header Injection

**What it is:** An attacker sends a forged `Host` header (e.g. `Host: evil.com`). If the application uses `request.base_url` or `request.headers["host"]` to build URLs (e.g. in password reset emails), the generated link points to the attacker's domain.

**Pending countermeasures:**
- [ ] Never build absolute URLs from `request.headers["host"]` — always use a hardcoded `BASE_URL` config value
- [ ] Add `BASE_URL` to the `.secrets.toml` config and validate it on startup
- [ ] Nginx: use `if ($host !~* "^noharm\.app$") { return 444; }` to reject requests with unexpected Host headers before they reach the app

**Where to implement:** `config.py`, `emailService.py`, Nginx config

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

**Pending countermeasures:**
- [ ] Add `pip-audit` or `safety` to the CI pipeline — fail the build if any dependency has a known CVE

```bash
# Add to GitHub Actions
pip install pip-audit
pip-audit -r requirements.txt
```

- [ ] Enable GitHub's Dependabot for automated dependency update PRs
- [ ] Review and update pinned versions at least monthly; prioritise security releases immediately
- [ ] Add a `requirements-dev.txt` for test/dev-only packages to reduce the production attack surface

**Where to implement:** `.github/workflows/`, `requirements.txt`

---

### 9.2 Secrets in Version Control

**What it is:** `.secrets.toml` contains the database password, encryption key, and JWT secrets. If this file is ever committed to Git (even once, even on a private repository), the secrets are permanently compromised — Git history retains all commits.

**Current state:** `.gitignore` includes `venv` and `__pycache__` but **does not explicitly ignore `.secrets.toml`**.

**Pending countermeasures:**
- [ ] **Immediately** add `.secrets.toml` and `.env*.local` to `.gitignore`
- [ ] Run `git log --all -- .secrets.toml` and `git log --all -- .env.local` to verify these files have never been committed
- [ ] If they have been committed, rotate all secrets immediately — assume they are compromised
- [ ] Add a pre-commit hook (e.g. `detect-secrets` or `git-secrets`) that blocks commits containing high-entropy strings or known secret patterns
- [ ] Consider using Vercel's encrypted environment variable storage instead of `.secrets.toml` for production deployments

**Where to implement:** `.gitignore`, CI pre-commit hooks

---

## 10. Implementation Status

### Implemented ✅

| Layer | Control |
|-------|---------|
| Transport | Security headers (CSP, HSTS, X-Frame-Options, etc.) |
| Transport | CORS origin whitelist |
| Authentication | JWT access + refresh tokens with unique JTI |
| Authentication | Persistent JWT blacklist (JSONL, SHA-256 hashed) |
| Authentication | Per-IP rate limiting (60 req/min, 60-min block) |
| Authentication | Per-username login rate limiting (5 attempts, 30-min lockout) |
| Data at rest | AES-256 field-level encryption for all sensitive columns |
| Data at rest | SHA-256 hash index for encrypted field lookups |
| Data at rest | Argon2 password hashing |
| Input validation | Pydantic schemas on all routes |
| Input sanitisation | HTML stripping via `bleach` |
| Error handling | Centralised `NoHarmException` — no stack traces leaked to clients |

### Pending ⬜

| Priority | Control | Section | Location |
|----------|---------|---------|----------|
| **Critical** | WebSocket JWT authentication | §6.1 | `socketManager.py` |
| **Critical** | Service-layer ownership checks (IDOR prevention) | §5.2 | all `*Service.py` |
| **Critical** | Stack trace removed from client error responses | §8.1 | all `*Repository.py`, `main.py` |
| **Critical** | `.secrets.toml` added to `.gitignore` | §9.2 | `.gitignore` |
| **Critical** | Verify secrets were never committed to Git | §9.2 | Git history audit |
| **High** | Refresh token persistence in database | §7.4 | new `refreshTokenRepository.py`, `userService.py` |
| **High** | Unified error message for login (account enumeration) | §7.1 | `authRoutes.py`, `userService.py` |
| **High** | Redis-backed rate limiting (multi-worker) | §4.1, §8.2 | `rateLimiter.py` |
| **High** | Constant-time login response (timing attack) | §1.2 | `authRoutes.py` |
| **High** | Refresh token rotation (invalidate old on refresh) | §1.1 | `authRoutes.py` |
| **High** | Per-endpoint rate limits | §4.1 | `middleware.py` |
| **High** | Structured log sanitisation | §5.1 | logging setup |
| **High** | Debug mode guard in production | §8.5 | `main.py`, `config.py` |
| **High** | pip-audit in CI pipeline | §9.1 | `.github/workflows/` |
| **Medium** | Email verification on registration | §7.2 | `userService.py`, `emailService.py` |
| **Medium** | Secure password reset flow | §7.3 | `userService.py`, `emailService.py` |
| **Medium** | Audit log integration in all services | §7.5 | all `*Service.py` |
| **Medium** | Request body size limit (Uvicorn + Nginx) | §8.3 | `run.py`, Nginx config |
| **Medium** | CAPTCHA after 3 login failures | §1.2 | `authRoutes.py` |
| **Medium** | `extra='forbid'` on all input schemas | §2.3 | all `*Schemas.py` |
| **Medium** | Nginx configuration (timeouts, body size, SSL) | §4.2 | infrastructure |
| **Medium** | Encryption key versioning and rotation strategy | §8.4 | `encryption.py`, `config.py` |
| **Medium** | File upload security (MIME validation, UUID rename, private bucket) | §8.7 | `storageService.py` |
| **Low** | Account enumeration protection on register endpoint | §7.1 | `userService.py` |
| **Low** | Host header injection protection | §8.6 | `config.py`, Nginx |
| **Low** | Dependabot / automated dependency update PRs | §9.1 | `.github/` |
| **Low** | 2FA / MFA | — | `authRoutes.py` |
| **Low** | `pre-commit` hook to block secrets in commits | §9.2 | `.pre-commit-config.yaml` |

---

## Dependency Reference

Security-critical packages and their purpose:

| Package | Version | Purpose |
|---------|---------|---------|
| `PyJWT` | 2.8.0 | JWT encoding / decoding |
| `argon2-cffi` | 23.1.0 | Password hashing (Argon2id) |
| `cryptography` | 41.0.7 | AES-256 (Fernet) field encryption |
| `bleach` | 6.1.0 | HTML sanitisation (XSS prevention) |
| `passlib[bcrypt]` | 1.7.4 | bcrypt fallback if needed |
| `python-jose[cryptography]` | 3.3.0 | Alternative JWT library (unused, available) |
| `pydantic[email]` | 2.5.0 | Input validation and type enforcement |
| `email-validator` | 2.1.0 | Email format validation |