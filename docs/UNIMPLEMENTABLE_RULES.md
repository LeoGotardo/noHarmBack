# Rules That Could Not Be Implemented in Routes / Services Only

The following rules from `docs/rules.md` require changes outside the route and service layers
(new database tables, new models, new repositories, or external services).
They are documented here so they can be tracked and implemented in a future sprint.

---

## Rule 1.1 — Email Verification Flow (§1.1)

**Rule**: "On successful registration, `status` is set to `STATUS_CODES['pending']` until email
verification is complete. The user is **not** allowed to access protected endpoints while
`status == pending`."

**What was implemented**: Registration correctly sets `status = pending` for users whose
Firebase token carries `emailVerified = false`, and `status = enabled` for already-verified
accounts.

**What is missing**:
- A backend-initiated email verification flow (send verification link, verify token).
- A middleware / dependency guard that rejects requests from `pending` users with `403`.

**Why it needs more than routes/services**:
- Sending verification emails requires `EmailService` (`src/infrastructure/external/emailService.py`),
  which is currently empty.
- Storing and validating verification tokens requires either a new DB table or an in-memory store.
- The `getCurrentUser` dependency (`src/api/dependencies/auth.py`) would need to also check the
  user's status, which means it needs a database lookup and changes to the dependency layer.

---

## Rule 2.2 — Refresh Token Database Storage (§2.2)

**Rule**: "Must be stored (hashed) in a `refreshTokens` table alongside `userId`, `expiresAt`,
and `deviceHint` (pending implementation — see `docs/security.md §7.4`)."

**What was implemented**: Refresh token rotation (old token is blacklisted on every `/auth/refresh`
call) is working via the existing `TokenBlacklist`.

**What is missing**:
- A `refresh_tokens` table (new Alembic migration + SQLAlchemy model).
- A `RefreshTokenRepository` to persist and look up hashed tokens.
- Storing the hashed refresh token on issue, and deleting (not just blacklisting) on rotation.
- A `deviceHint` field to support per-device logout.

**Why it needs more than routes/services**:
- Requires a new database model and migration.
- Requires a new repository class.
- Both the `JwtHandler` and `AuthService` would need to coordinate with the new repository.

---

## Rule 7.2 — Badge Milestone Rules (§7.2)

**Rule**: "One Week / One Month / Three Months / Six Months / One Year / Comeback badges."

**What was implemented**: `BadgeService.checkAndGrantBadges(userId)` is called after every
streak update (after `startStreak`, `endStreak`, and `checkin`). The method is a no-op
placeholder (`pass`).

**What is missing**:
- The actual badge seeding (the badge records must exist in `tb_5`).
- Duration-based milestone checks comparing the ended streak's length against each threshold.
- The "Comeback" badge (check whether any previous streak exists before granting).

**Why it needs more than routes/services**:
- The badge seed data must be inserted into the database (migration or seed script).
- Without the badge rows in `tb_5`, `UserBadgesRepository.grant()` will fail on FK constraint.
- Implementing `checkAndGrantBadges` fully is possible in `streakService.py` alone, **but**
  requires those badge seed records to exist first.
- Once the seed data is in place, `_checkAndGrantBadges` in `streakService.py` can be filled in
  without any further infrastructure changes.

---

## Rule 8.1 — Audit Log for Password Change (type=3) and Email Change (type=4) (§8.1)

**Rule**: Password and email changes must produce audit log entries of type 3 and 4 respectively.

**What was implemented**: Login (type=1), failed login (type=2), logout/token revocation (type=6),
streak reset (type=7), and account status change (type=5) are all logged.

**What is missing**:
- Password change endpoint — authentication is handled by Firebase; there is no backend
  password-change endpoint to instrument.
- Email change endpoint — `docs/rules.md §1.3` marks this as "pending implementation"
  and requires a full email-change verification flow.

**Why it needs more than routes/services**:
- Password management is delegated to Firebase and cannot be intercepted at the service layer.
- Email change requires the `EmailService` (see Rule 1.1 above).

---

## Note on Rule 9.5 — UUID v4 Primary Keys

All new records created in the updated services use `UserModel`, `StreakModel`, `FriendshipModel`,
`ChatModel`, and `MessageModel` directly. The models generate UUIDs via `default=uuid.uuid4`.
The `id` field is intentionally omitted from the constructor calls so the DB default fires.

> If a caller explicitly passes an `id`, the passed value is used (required for `register`
> where the Firebase UID is used as the user's primary key).
