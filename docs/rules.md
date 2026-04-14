# NoHarm — Business Rules

This document defines all business rules enforced by the NoHarm backend. Every rule listed here must be validated at the **service layer** before any repository call is made. Rules are grouped by domain entity.

---

## 1. Users

### 1.1 Registration
- `username` must be between 3 and 50 characters and match `^[a-zA-Z0-9_-]+$`.
- `email` must be a valid RFC-5321 address (validated via `pydantic[email]`).
- `password` must be at least 8 characters.
- Both `username` and `email` must be globally unique. If either already exists, the registration must fail with `409 Conflict`. The error message must **not** reveal which field is duplicated (account enumeration prevention — see `docs/security.md §7.1`).
- On successful registration, `status` is set to `STATUS_CODES["pending"]` until email verification is complete. The user is **not** allowed to access protected endpoints while `status == pending` (this will be implemented in a future release).
- Password is hashed with Argon2id via `Encryption.encryptPass()` before being stored. The plaintext password is never persisted.

### 1.2 Login
- Login is performed by google firebase with google's account linking mechanism.
- The system must look up the user by the SHA-256 hash of the email (encrypted field lookup pattern).
.
- On success, `LoginRateLimiter.onSuccess(email)` must be called to clear the attempt counter.
- On failure, the response must always be `"Invalid credentials"` regardless of whether the email exists or the password is wrong (account enumeration prevention).
- After 5 failed attempts within 15 minutes, the account is locked for 30 minutes.
- On successful login, an `access token` (15 min) and a `refresh token` (7 days) are issued.

### 1.3 Profile Updates
- Only `username` and `profilePicture` may be updated by the user.
- `email` changes must trigger a new verification flow (pending implementation).
- `status` may only be changed via dedicated admin endpoints or internal service logic — never via the standard update endpoint.

### 1.4 Account Status Transitions

| From | To | Trigger |
|------|----|---------|
| `pending` | `enabled` | Email verification confirmed (implemented in a future release) |
| `enabled` | `blocked` | Admin action |
| `enabled` | `banned` | Admin action |
| `enabled` | `deleted` | User soft-deletes account |
| `blocked` | `enabled` | Admin action |

- A `deleted`, `banned`, or `blocked` user must be rejected at the authentication layer with `403 Forbidden`.

---

## 2. Authentication & Tokens

### 2.1 Access Token
- Lifetime: 15 minutes.
- Signed with `JWT_SECRET_KEY`.
- Contains claims: `sub` (userId), `type: "access"`, `exp`, `iat`, `jti`.
- Must be sent in the `Authorization: Bearer <token>` header on every protected request.

### 2.2 Refresh Token
- Lifetime: 7 days.
- Signed with `JWT_REFRESH_SECRET_KEY`.
- Must be stored (hashed) in a `refreshTokens` table alongside `userId`, `expiresAt`, and `deviceHint` (pending implementation — see `docs/security.md §7.4`).
- On `POST /auth/refresh`:
  1. Verify the token signature and expiry.
  2. Look up the hashed token in the database.
  3. Delete the old record (rotation — single use).
  4. Issue a new `access token` + `refresh token` pair.

### 2.3 Logout
- Both the `access token` and the `refresh token` must be added to the `TokenBlacklist` via `jwtHandler.revokeToken(jti, exp)`.
- Blacklisted tokens are checked on every request by `verifyAccessToken`.

### 2.4 Token Blacklist
- JTIs are stored as SHA-256 hashes — plaintext JTIs are never written to disk.
- Expired entries are removed on startup via `TokenBlacklist.cleanup()`.

---

## 3. Friendships

### 3.1 Sending a Friend Request
- A user may **not** send a friend request to themselves.
- A user may **not** send a friend request if any friendship (in any status) already exists between the two users — checked via `FriendshipRepository.existsByUsers(senderID, receiverID)` unless the status is `deleted` (soft delete {what indicates a removed friendship}).
- On creation, `status` is set to `STATUS_CODES["pending"]`.
- `sendAt` is set to `datetime.utcnow()` at the time of creation.

### 3.2 Responding to a Request
- Only the **receiver** may accept or reject a pending request.
- Accepting sets `status = STATUS_CODES["accepted"]` and `recivedAt = datetime.utcnow()`.
- Rejecting (ignoring) sets `status = STATUS_CODES["ignored"]`.

### 3.3 Blocking
- Either participant may block the other at any time, regardless of current friendship status.
- Blocking sets `status = STATUS_CODES["blocked"]`.
- A blocked user may **not** send a new friend request to the blocker.
- A bloqued user may **not** load the blocker's profile.

### 3.4 Chat Pre-condition
- Two users may **only** start a chat if a friendship with `status == STATUS_CODES["accepted"]` exists between them.
- This check must be performed in `ChatService.create()` before calling `ChatRepository.create()`.

---

## 4. Chats

### 4.1 Creation
- A chat may only be created between two users who are **accepted friends** (see §3.4).
- A chat is created with `status = STATUS_CODES["pending"]` (awaiting first message or explicit acceptance).
- There must be **no active chat** (status `enabled` or `pending`) already existing between the two users. If one exists, the service must return it instead of creating a duplicate.
- `startedAt` is set to `datetime.utcnow()` at creation.

### 4.2 Ending a Chat
- Either participant may end (close) the chat.
- Ending sets `endedAt = datetime.utcnow()` and `status = STATUS_CODES["disabled"]`.
- No new messages may be sent to a chat with `status != enabled`.

### 4.3 Access Control
- Only the two participants (sender and receiver) may read or write messages in a chat.
- This is enforced at the database level via RLS policy `chats_participant_data` on `tb_3`.

---

## 5. Messages

### 5.1 Sending
- A message may only be sent to an **active chat** (`status == STATUS_CODES["enabled"]`).
- The `sender` field must match the authenticated user's ID — a user may not send messages on behalf of another.
- Message content is sanitised with `Sanitizer.cleanHtml()` before persistence.
- Message content must not be empty after sanitisation.
- On creation, `status` is set to `STATUS_CODES["unread"]` and `sendAt = datetime.utcnow()`.

### 5.2 Reading
- Only the **chat participants** may retrieve messages (enforced via RLS on `tb_4`).

### 5.3 Marking as Read
- When `markAsRead(messageId)` is called, `status` changes from `unread → read` and `recivedAt = datetime.utcnow()`.
- `markAllAsRead(chatId)` applies the same transition to all `unread` messages in the chat.
- A message that is already `read` must not be updated again.

---

## 6. Streaks

### 6.1 Creation
- A user may only have **one active streak** at a time (`status == STATUS_CODES["enabled"]`).
- Attempting to create a new streak when one already exists must return a `409 Conflict`.
- `start` is set to `datetime.utcnow()`.
- `isRecord` is set to `False` on creation.

### 6.2 Ending (Reset)
- Ending a streak sets `end = datetime.utcnow()` and `status = STATUS_CODES["disabled"]`.
- After ending, the service must automatically create a new streak for the user (continuity of tracking).
- After ending, the service must check if the ended streak is longer than the current record (`isRecord == True`). If so, it calls `StreakRepository.markAsRecord(streakId)` — setting `isRecord = True` on the new record and `False` on the previous one.

### 6.3 Expiry (Auto-Reset)
- If more than 24 hours have passed since the last update of an active streak without any user activity, the streak is automatically expired (reset) the next time the user fetches `getCurrentStreak`.
- Expiry follows the same flow as a manual reset (§6.2).

### 6.4 Record
- Only one streak per user may have `isRecord == True` at any given time.
- `markAsRecord` must unset the previous record before setting the new one.

---

## 7. Badges

### 7.1 Granting
- Badges are granted automatically by `BadgeService.checkAndGrantBadges(userId)`, which is called after every streak update.
- A badge is only granted once per user — checked via `UserBadgesRepository.existsByUserAndBadge()`.
- `givenAt` is set to `datetime.utcnow()` at the time of granting.

### 7.2 Milestone Rules

All milestones will be implemented in a future release.

### 7.3 Revoking
- Revoking sets `status = STATUS_CODES["deleted"]` on the `UserBadge` record.
- The badge entry is **not** hard-deleted so audit history is preserved.

---

## 8. Audit Logs

### 8.1 When to Log
Every service method that performs a sensitive action must create an audit log entry via `AuditLogsService.create()`. The following actions are mandatory:

| Action | `type` code |
|--------|-------------|
| Successful login | 1 |
| Failed login attempt | 2 |
| Password change | 3 |
| Email change | 4 |
| Account status change | 5 |
| Token revocation (logout) | 6 |
| Streak reset | 7 |
| Badge granted | 8 |
| Admin action | 9 |

The `type` list can be extended if needed to include neew actions like system maintenance and secirity breaches.

### 8.2 Immutability
- Audit log entries must **never be hard-deleted**.
- The `status` field may be updated (e.g. `disabled`) but the record must remain in the database.
- `description` is stored encrypted (AES-256) to protect sensitive details at rest.

### 8.3 Access
- A user may only read their own audit logs (enforced via RLS policy `audit_logs_own_data` on `tb_7`).
- Administrators may query logs by `catalystId`, `type`, or date range.

---

## 9. Cross-Cutting Rules

### 9.1 Soft Delete
- No entity is ever hard-deleted by default. Deletion sets `status = STATUS_CODES["deleted"]`.
- Deleted entities are invisible to standard queries and to RLS-filtered sessions.

### 9.2 Ownership Checks
- Every service method that reads or mutates a resource must verify that the authenticated user owns or is a participant of that resource **before** executing the repository call.
- Relying solely on RLS is not sufficient — application-level ownership checks are required as defence-in-depth.

### 9.3 Input Sanitisation
- All free-text user input (message content, usernames, descriptions) must pass through `Sanitizer.cleanHtml()` before being stored.

### 9.4 Status Code Reference

| Name | Value | Used In |
|------|-------|---------|
| `disabled` | 0 | User, streak, badge |
| `enabled` | 1 | User, streak |
| `deleted` | 2 | All entities (soft delete) |
| `blocked` | 3 | User, friendship |
| `pending` | 4 | Friendship, chat, user (unverified) |
| `accepted` | 5 | Friendship |
| `ignored` | 6 | Friendship (rejected request) |
| `unread` | 7 | Message |
| `read` | 8 | Message |
| `banned` | 9 | User |

### 9.5 UUID Keys
- All primary keys are UUID v4. Sequential integer IDs must never be used (IDOR prevention).

### 9.6 Rate Limiting
- Global: 60 requests / 60 seconds per IP. Excess → 60-minute block.
- Login endpoint: 5 attempts / 15 minutes per username. Excess → 30-minute lockout.
- WebSocket messages: max 20 messages / minute per authenticated user (pending implementation).