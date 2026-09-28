from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from domain.services.consentService import ConsentService
from infrastructure.database.models.userModel import UserModel
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from schemas.authSchemas import AuthRegisterRequest, AuthLoginRequest
from security.jwtHandler import JwtHandler
from security.tokenBlacklist import TokenBlacklist
from security.rateLimiter import LoginRateLimiter
from security.sanitizer import Sanitizer
from security.firebaseIdentity import verifyIdToken
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database

import re
from datetime import date, datetime, timedelta, timezone

_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]{3,50}$')


def _ageOn(birthDate: date, today: date) -> int:
    """Whole years between two dates.

    Written out rather than `days // 365`: that drifts a day every four years
    and turns the birthday of anyone born on 29 February into a value that is
    right three years in four.
    """
    years = today.year - birthDate.year
    if (today.month, today.day) < (birthDate.month, birthDate.day):
        years -= 1
    return years


_blacklist = TokenBlacklist()
_jwtHandler = JwtHandler(_blacklist)
_loginLimiter = LoginRateLimiter()


class AuthService:
    def __init__(self, db):
        self.db: Database = db
        self.userRepository = UserRepository(db)  
        self.auditRepository = AuditLogsRepository(db)  
        self.consentService = ConsentService(db)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _logAudit(self, actionType: int, catalystId: str, description: str) -> None:
        """Create an audit log entry. Failures are silently ignored to not block main flow."""
        try:
            entry = AuditLogsModel(
                type=actionType,
                catalyst_id=catalystId,
                catalyst=None,
                description=description
            )
            self.auditRepository.create(entry)  
        except Exception:
            pass

    def _deletionDeadline(self, user) -> datetime | None:
        """When a soft-deleted account stops being restorable.

        None when the row carries no `deleted_at` — accounts deleted before the
        grace window existed, if any survived the backfill in migration
        `20260901_01`. Those are treated as already gone rather than restorable:
        offering a restore whose deadline cannot be stated is worse than not
        offering one.
        """
        if user.deleted_at is None:
            return None

        return user.deleted_at + timedelta(days=config.ACCOUNT_DELETION_GRACE_DAYS)

    def _pendingDeletionError(self, user) -> NoHarmException:
        """The 403 that tells a client an account is restorable, and until when.

        Carries its own errorCode and a deadline because the app has to draw a
        different screen for this than for a real rejection: "restore your
        account?" rather than "account not found". The routes let this reach the
        NoHarmException handler unconverted so `details` survives.
        """
        deadline = self._deletionDeadline(user)

        if deadline is None or deadline <= datetime.now(timezone.utc).replace(tzinfo=None):
            # Window closed, or never opened. The purge has not caught up yet,
            # but as far as anyone outside is concerned the account is gone.
            self._logAudit(2, str(user.id), "Failed login — deletion window closed")
            return NoHarmException(statusCode=403, errorCode="ACCOUNT_DELETED", message="Account not found.")

        return NoHarmException(
            statusCode=403,
            errorCode="ACCOUNT_PENDING_DELETION",
            message="This account is scheduled for deletion. Restore it to continue.",
            details={"deletionScheduledAt": deadline.isoformat() + "Z"}
        )

    def _liftExpiredSuspension(self, user):
        """Re-enable an account whose suspension has run out, and return it.

        Called at the top of every path that decides whether someone may come
        back in. A suspension ends by being *used*, not by a cron: there is
        nothing to do for an account nobody is signing in to, and a nightly
        sweep is one more thing that can quietly stop running while the app
        keeps refusing people whose time is up.

        Returns the user unchanged when there is nothing to lift.
        """
        if user.status != config.STATUS_CODES["banned"]:
            return user
        if user.banned_until is None:
            return user  # permanent
        if user.banned_until > datetime.now(timezone.utc).replace(tzinfo=None):
            return user  # still serving it

        restored = self.userRepository.liftExpiredSuspension(str(user.id))
        if restored is None:
            return user

        self._logAudit(5, str(user.id), f"Suspension expired for user {user.id}; account re-enabled")
        return restored

    def _syncProfilePicture(self, user, picture: str | None) -> None:
        """Keep the profile picture in step with the Google account.

        It used to be read once, at registration, and never again: an account
        that registered before the claim carried a photo — or whose photo URL
        Google later rotated — showed a blank avatar for ever, and with no
        upload endpoint there was nothing the user could do about it. Sourced
        from the verified token claim, never from the request body.

        Best effort: a failed write must not cost anyone their sign-in.
        """
        if not picture or picture == user.profile_picture:
            return
        # A blocked picture is blocked against Google too. This sync is exactly
        # the path that would undo a moderator's decision, silently, at the
        # user's next sign-in.
        if getattr(user, "picture_blocked", False):
            return
        try:
            userModel = self.userRepository.findById(str(user.id), returnModel=True)
            userModel.profile_picture = picture
            self.userRepository.session.commit()
        except Exception:
            self.userRepository.session.rollback()

    def _bannedError(self, user) -> NoHarmException:
        """The 403 for a banned account — with the end date when it has one.

        A permanent ban and a three-day suspension are the same status, and
        answering both with "Account is banned." tells someone serving 72 hours
        that they have lost the account. The date is the whole difference, so
        it travels in `details` the way the deletion deadline does, and the app
        draws "you can come back on <date>" instead of a dead end.
        """
        if user.banned_until is None:
            return NoHarmException(
                statusCode=403,
                errorCode="ACCOUNT_BANNED",
                message="Account is banned."
            )

        return NoHarmException(
            statusCode=403,
            errorCode="ACCOUNT_SUSPENDED",
            message="This account is suspended. You can sign in again when it ends.",
            details={"suspendedUntil": user.banned_until.isoformat() + "Z"}
        )

    def _requireConsent(self, request: AuthRegisterRequest) -> None:
        """Refuse a registration that agreed to nothing.

        The terms and the privacy policy are a condition of holding an account,
        so both are checked here. Health-data consent is not: declining it
        creates a working account without the streak tracker, which is what
        makes it a real choice rather than a checkbox in the way of the button.
        """
        missing = []
        if not request.acceptedTerms:
            missing.append("terms")
        if not request.acceptedPrivacy:
            missing.append("privacy")

        if missing:
            raise NoHarmException(
                statusCode=400,
                errorCode="CONSENT_REQUIRED",
                message="The terms of use and the privacy policy must both be accepted.",
                details={"missing": missing}
            )

    def _requireMinimumAge(self, birthDate: date) -> None:
        """Refuse an account below MINIMUM_AGE_YEARS, and refuse a bad date.

        Self-declared — no provider this app uses carries an age claim — so
        this is not verification. It is the record that the question was asked
        and answered, and the refusal of an answer that says no.

        A future date is rejected separately from being under age: it is a
        broken client or a typo, and telling someone born in 2035 that they are
        too young is a worse answer than telling them the date is wrong.
        """
        today = datetime.now(timezone.utc).date()

        if birthDate > today:
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_BIRTH_DATE",
                message="That date of birth is in the future."
            )

        minimum = config.MINIMUM_AGE_YEARS
        if _ageOn(birthDate, today) < minimum:
            raise NoHarmException(
                statusCode=403,
                errorCode="UNDERAGE",
                message=f"You must be at least {minimum} to use NoHarm.",
                details={"minimumAge": minimum}
            )

    # ── register ──────────────────────────────────────────────────────────────

    def register(self, request: AuthRegisterRequest) -> dict:
        """Create a new user account from a verified Firebase identity.

        Rules (§1.1):
        - the ID token is verified first: uid, email and email_verified come
          from its claims, so an account cannot be created for a UID the caller
          does not control, and verification cannot be self-declared
        - the terms and the privacy policy must both be accepted, and the
          declared age must reach MINIMUM_AGE_YEARS; both are refused before
          anything is written, because an account that exists having agreed to
          nothing is the state this check exists to make impossible
        - username must match ^[a-zA-Z0-9_-]+$ and be 3–50 chars
        - username and email must be globally unique → 409 (generic message)
        - status = pending until email verification (enabled if Firebase already verified)
        - password is never stored here (Firebase handles auth)

        Returns:
            dict with accessToken, refreshToken, tokenType
        """
        identity = verifyIdToken(request.idToken)

        uid: str = identity.uid
        username: str = request.username
        email: str | None = identity.email

        # Before anything is written. A row created first and gated afterwards
        # is an account that exists without having agreed to anything, and the
        # only way back out of that state is a hand-written DELETE.
        self._requireConsent(request)
        self._requireMinimumAge(request.birthDate)

        # Google always sends one, but a provider that does not would leave the
        # account without the field every uniqueness rule below keys on.
        if not email:
            raise NoHarmException(
                statusCode=400,
                errorCode="EMAIL_REQUIRED",
                message="This sign-in method does not provide an email address."
            )

        # Rule 1.1 — username format (3–50 chars, ^[a-zA-Z0-9_-]+$)
        username = Sanitizer.cleanHtml(username)
        if not _USERNAME_RE.match(username):
            raise NoHarmException(
                statusCode=400,
                errorCode="INVALID_USERNAME",
                message="Username must be 3–50 characters and contain only letters, numbers, _ or -."
            )
            
        # Rule 1.1 / 1.4 — the UID is checked first: it is the primary key, so
        # registering twice with the same Google account used to reach the
        # INSERT and die there. A row already here is one of three things, and
        # each answers differently.
        try:
            existing = self.userRepository.findById(uid)
        except NoHarmException as e:
            if e.statusCode != 404:
                raise e
            existing = None  # 404 → uid is available, continue

        if existing is not None:
            # A suspension that has run out is lifted here, before anything
            # reads the status: otherwise registering again after serving one
            # answers "banned" for an account that is no longer banned.
            existing = self._liftExpiredSuspension(existing)

            # Banned first: a banned account must not be able to talk its way
            # back in through any branch below.
            if existing.status == config.STATUS_CODES["banned"]:
                raise self._bannedError(existing)

            # Deleted and still inside the grace window — registering again is
            # the same gesture as signing in, so it is answered the same way:
            # the client is told the account is restorable and with what
            # deadline, and POST /auth/reactivate is the one thing that undoes
            # it. Registering does not silently resurrect the account: someone
            # who deleted after a relapse should not have their profile handed
            # back to their friends without saying so.
            if existing.status == config.STATUS_CODES["deleted"]:
                raise self._pendingDeletionError(existing)

            raise NoHarmException(statusCode=409, errorCode="CONFLICT", message="Registration failed. Please check your details.")

        try:
            self.userRepository.findByEmail(email)
            raise NoHarmException(statusCode=409, errorCode="CONFLICT", message="Registration failed. Please check your details.")
        except NoHarmException as e:
            if e.statusCode != 404:
                raise e
            # 404 → email is available, continue

        try:
            self.userRepository.findByUsername(username)
            raise NoHarmException(statusCode=409, errorCode="CONFLICT", message="Registration failed. Please check your details.")
        except NoHarmException as e:
            if e.statusCode != 404:
                raise e
            # 404 → username is available, continue

        photoUrl = identity.picture
        status = config.STATUS_CODES["enabled"] if identity.emailVerified else config.STATUS_CODES["pending"]

        newUser = UserModel(
            id=uid,
            username=username,
            email=email,
            profile_picture=photoUrl,
            status=status,
            birth_date=request.birthDate
        )
        self.userRepository.create(newUser)

        # After the user row, because the consent rows carry a foreign key into
        # it. Not best-effort: an account whose consents failed to write is an
        # account the gate stops at its next launch, with the user re-accepting
        # something they already accepted and no way to tell why. A failure here
        # raises, and the registration is reported as failed.
        self.consentService.recordRegistrationConsents(uid, request.healthDataConsent)

        accessToken = _jwtHandler.createAccessToken(uid)
        refreshToken = _jwtHandler.createRefreshToken(uid)

        return {
            "accessToken": accessToken,
            "refreshToken": refreshToken,
            "tokenType": "Bearer"
        }

    # ── login ─────────────────────────────────────────────────────────────────

    def login(self, request: AuthLoginRequest) -> dict:
        """Authenticate via Firebase identity and issue token pair.

        Rules (§1.2, §1.4, §8.1):
        - the ID token is verified before anything else — the UID is read from
          its claims, never from the body, because the UID is public (it is the
          user id the API returns in friend lists and search) and would
          otherwise be a password anyone could look up
        - Rate-limited per UID (5 attempts / 15 min → 30 min lockout)
        - banned / blocked / deleted accounts → 403
        - On failure: generic 'Invalid credentials' response
        - On success: audit log type=1; on failure: type=2

        Returns:
            dict with accessToken, refreshToken, tokenType
        """
        identity = verifyIdToken(request.idToken)
        uid: str = identity.uid

        # Rate limiting (§9.6)
        allowed, reason = _loginLimiter.check(uid)
        if not allowed:
            raise NoHarmException(statusCode=429, errorCode="TOO_MANY_REQUESTS", message=reason)

        genericError = NoHarmException(
            statusCode=401,
            errorCode="INVALID_CREDENTIALS",
            message="Invalid credentials."
        )

        try:
            user = self.userRepository.findById(uid)
        except NoHarmException:
            self._logAudit(2, uid, "Failed login — user not found")
            raise genericError

        user = self._liftExpiredSuspension(user)

        # Rule 1.4 — reject banned / blocked / deleted
        blocked_statuses = {
            config.STATUS_CODES.get("banned"),
            config.STATUS_CODES.get("blocked"),
            config.STATUS_CODES.get("deleted"),
        }
        if user.status in blocked_statuses:
            self._logAudit(2, str(user.id), f"Failed login — account status {user.status}")
            match user.status:
                case s if s == config.STATUS_CODES.get("banned"):
                    raise self._bannedError(user)
                case s if s == config.STATUS_CODES.get("blocked"):
                    raise NoHarmException(statusCode=403, errorCode="ACCOUNT_BLOCKED", message="Account is blocked.")
                case _:
                    # Deleted splits in two: still inside the grace window, so
                    # the client can offer a restore, or past it, in which case
                    # the answer is the same "Account not found." it always was.
                    raise self._pendingDeletionError(user)

        _loginLimiter.onSuccess(uid)
        self._syncProfilePicture(user, identity.picture)
        self._logAudit(1, str(user.id), "Successful login")

        accessToken = _jwtHandler.createAccessToken(str(user.id))
        refreshToken = _jwtHandler.createRefreshToken(str(user.id))

        return {
            "accessToken": accessToken,
            "refreshToken": refreshToken,
            "tokenType": "Bearer"
        }

    # ── reactivate ────────────────────────────────────────────────────────────

    def reactivate(self, idToken: str) -> dict:
        """Undo a deletion that is still inside its grace window (§1.4).

        Deliberately a separate call rather than something login does on its
        own. Deleting an account here is often a hard moment — a relapse, a
        withdrawal from the whole idea of being seen — and silently restoring
        the profile, the friend list and the presence of someone who only meant
        to sign in would hand their account back to their friends without ever
        asking. So the app shows what will happen and the user says yes.

        Rejects anything that is not a deleted account inside the window:
        - banned → 403, and a deletion never launders a ban
        - already active → 409, nothing to restore
        - window closed → the same "Account not found." an absent row gets,
          because the purge is the only thing left to happen to it

        Returns:
            dict with accessToken, refreshToken, tokenType
        """
        uid: str = verifyIdToken(idToken).uid

        # Same bucket as login: reactivation is an unauthenticated,
        # UID-addressed entry point, so it gets the same brute-force ceiling.
        allowed, reason = _loginLimiter.check(uid)
        if not allowed:
            raise NoHarmException(statusCode=429, errorCode="TOO_MANY_REQUESTS", message=reason)

        try:
            user = self.userRepository.findById(uid)
        except NoHarmException as e:
            if e.statusCode != 404:
                raise e
            raise NoHarmException(statusCode=403, errorCode="ACCOUNT_DELETED", message="Account not found.")

        user = self._liftExpiredSuspension(user)

        if user.status == config.STATUS_CODES["banned"]:
            self._logAudit(2, str(user.id), "Failed reactivation — account banned")
            raise self._bannedError(user)

        if user.status == config.STATUS_CODES["blocked"]:
            raise NoHarmException(statusCode=403, errorCode="ACCOUNT_BLOCKED", message="Account is blocked.")

        if user.status != config.STATUS_CODES["deleted"]:
            raise NoHarmException(
                statusCode=409,
                errorCode="ACCOUNT_NOT_DELETED",
                message="This account is already active."
            )

        deadline = self._deletionDeadline(user)
        if deadline is None or deadline <= datetime.now(timezone.utc).replace(tzinfo=None):
            self._logAudit(2, str(user.id), "Failed reactivation — deletion window closed")
            raise NoHarmException(statusCode=403, errorCode="ACCOUNT_DELETED", message="Account not found.")

        restored = self.userRepository.restore(uid)

        _loginLimiter.onSuccess(uid)
        self._logAudit(5, str(restored.id), "Account restored within the deletion grace window")

        return {
            "accessToken": _jwtHandler.createAccessToken(str(restored.id)),
            "refreshToken": _jwtHandler.createRefreshToken(str(restored.id)),
            "tokenType": "Bearer"
        }

    # ── refresh ───────────────────────────────────────────────────────────────

    def refresh(self, refreshToken: str) -> dict:
        """Rotate refresh token and issue new token pair (§2.2).

        Returns:
            dict with new accessToken, refreshToken, tokenType
        """
        payload = _jwtHandler.verifyToken(refreshToken, "refresh")
        if not payload:
            raise NoHarmException(
                statusCode=401,
                errorCode="INVALID_TOKEN",
                message="Invalid or expired refresh token."
            )

        # Rotate: revoke old refresh token (§2.2)
        _jwtHandler.revokeToken(payload["jti"], payload["exp"])

        userId = payload["sub"]

        # §1.4 — a deleted/banned/blocked account must not be able to mint a new
        # token pair. Without this, soft-deleting an account left it live for as
        # long as the client kept refreshing.
        try:
            user = self.userRepository.findById(userId)
        except NoHarmException:
            raise NoHarmException(
                statusCode=401,
                errorCode="INVALID_TOKEN",
                message="Invalid or expired refresh token."
            )

        # A refresh is the app asking "am I still allowed in?" every 15
        # minutes, so it is also where a served suspension ends for someone who
        # left the app open: they get a new token pair instead of being logged
        # out and made to sign in again.
        user = self._liftExpiredSuspension(user)

        if user.status in {
            config.STATUS_CODES.get("banned"),
            config.STATUS_CODES.get("blocked"),
            config.STATUS_CODES.get("deleted"),
        }:
            raise NoHarmException(
                statusCode=403,
                errorCode="ACCOUNT_UNAVAILABLE",
                message="Account is not active."
            )

        return {
            "accessToken": _jwtHandler.createAccessToken(userId),
            "refreshToken": _jwtHandler.createRefreshToken(userId),
            "tokenType": "Bearer"
        }

    # ── logout ────────────────────────────────────────────────────────────────

    def logout(self, accessToken: str, refreshToken: str) -> None:
        """Revoke both tokens and write audit log type=6 (§2.3, §8.1)."""
        userId = None

        for token, tokenType in [(accessToken, "access"), (refreshToken, "refresh")]:
            payload = _jwtHandler.verifyToken(token, tokenType)
            if payload:
                if tokenType == "access":
                    userId = payload.get("sub")
                _jwtHandler.revokeToken(payload["jti"], payload["exp"])

        if userId:
            self._logAudit(6, userId, "Token revocation — logout")
