from infrastructure.database.repositories.consentRepository import ConsentRepository
from infrastructure.database.repositories.streakRepository import StreakRepository
from infrastructure.database.repositories.userRepository import UserRepository
from infrastructure.database.repositories.auditLogsRepository import AuditLogsRepository
from infrastructure.database.models.auditLogsModel import AuditLogsModel
from domain.entities.consent import Consent
from exceptions.baseExceptions import NoHarmException
from core.config import config
from core.database import Database

from datetime import datetime, timezone


TERMS = "terms"
PRIVACY = "privacy"
HEALTH_DATA = "health_data"

# Everything an account can be asked about. Order is the order the app shows
# them in, and the order they are recorded at registration.
DOCUMENTS = (TERMS, PRIVACY, HEALTH_DATA)

# The two that gate the app. Health data is deliberately not here: it is
# withdrawable, and an account that withdrew it has *answered* the question —
# blocking on it would make withdrawal a thing the user cannot actually do.
REQUIRED_DOCUMENTS = (TERMS, PRIVACY)

# 13 records an agreement, 14 records taking one back. Two types rather than
# one with a direction, because the question asked of the audit log is almost
# always "when did this account agree to X", and a single type answers it with
# a list the reader has to filter.
_AUDIT_CONSENT_GIVEN = 13
_AUDIT_CONSENT_WITHDRAWN = 14


def _utcNow() -> datetime:
    """Now, as the naive UTC the schema stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ConsentService:
    """What the account has agreed to, and what it still owes an answer on.

    Three documents, and the third is the reason this is a service rather than
    three columns:

    - `terms` and `privacy` gate the app. An account that has not accepted the
      current version of both sees the consent screen and nothing else.
    - `health_data` gates the streak tracker alone. A clean-day count is a
      record of someone's recovery from addiction — health data — so it needs
      consent that is explicit, given **separately** from the terms, and
      withdrawable without closing the account. Withdrawing it deletes the
      streaks it covered, which is what makes the word mean anything.

    ## Versions, not booleans

    A consent records the version that was live when it was given. Publishing a
    new version is a config change (`TERMS_VERSION` and friends) and nothing
    else: every stored row goes stale by comparison and the gate reappears. A
    boolean would mean an account had agreed, once, to a text that has since
    been rewritten — which is the failure this whole table exists to avoid.

    ## Stale health consent is pending; absent health consent is not

    An account that never gave health consent, or withdrew it, is not nagged:
    it answered. An account with an **active** consent at an old version is
    asked again, because it is still using the feature the document describes.
    """

    def __init__(self, db):
        self.database: Database = db
        self.consentRepository = ConsentRepository(self.database)
        self.streakRepository = StreakRepository(self.database)
        self.userRepository = UserRepository(self.database)
        self.auditRepository = AuditLogsRepository(self.database)

    def _logAudit(self, actionType: int, catalystId: str, description: str) -> None:
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

    # ── current versions ──────────────────────────────────────────────────────

    @staticmethod
    def currentVersion(document: str) -> str:
        """The version of one document an account is asked to accept today."""
        match document:
            case "terms":
                return config.TERMS_VERSION
            case "privacy":
                return config.PRIVACY_VERSION
            case "health_data":
                return config.HEALTH_CONSENT_VERSION
            case _:
                raise NoHarmException(
                    statusCode=400,
                    errorCode="UNKNOWN_DOCUMENT",
                    message="Unknown document."
                )

    @classmethod
    def currentVersions(cls) -> dict[str, str]:
        return {document: cls.currentVersion(document) for document in DOCUMENTS}

    # ── reads ─────────────────────────────────────────────────────────────────

    def summary(self, userId: str) -> dict:
        """The two answers every request needs, from one query.

        `pending` is what blocks the app; `healthDataConsent` is what the
        tracker reads. Both are derived here rather than in the client, so a
        patched app cannot decide it has already agreed.

        `GET /users/me` calls this on every profile load, which is why it does
        not also fetch the history that `status` returns.
        """
        current = self.consentRepository.findCurrent(userId)

        return {
            "pending": self._pending(current),
            "healthDataConsent": self._healthActive(current),
        }

    def status(self, userId: str) -> dict:
        """`summary`, plus the versions in force and the full history.

        What the privacy screen shows: not only whether something is owed, but
        everything this account ever agreed to and when — including the rows it
        later withdrew.
        """
        return {
            "versions": self.currentVersions(),
            "consents": list(self.consentRepository.findByUser(userId)),
            **self.summary(userId),
        }

    def pending(self, userId: str) -> list[str]:
        return self.summary(userId)["pending"]

    def hasHealthDataConsent(self, userId: str) -> bool:
        return self.summary(userId)["healthDataConsent"]

    def _pending(self, current: dict[str, Consent]) -> list[str]:
        pending: list[str] = []

        for document in REQUIRED_DOCUMENTS:
            consent = current.get(document)
            # Withdrawing a required consent is not offered anywhere — the way
            # to withdraw those is to delete the account — but a withdrawn row
            # has to read as "owes an answer" rather than as an agreement, or a
            # future path that does withdraw one would silently keep the app
            # unlocked.
            if consent is None or not consent.active or consent.version != self.currentVersion(document):
                pending.append(document)

        health = current.get(HEALTH_DATA)
        # Only when it is live and out of date. Never given and withdrawn are
        # both answers, and re-asking is nagging someone for opting out.
        if health is not None and health.active and health.version != self.currentVersion(HEALTH_DATA):
            pending.append(HEALTH_DATA)

        return pending

    @staticmethod
    def _healthActive(current: dict[str, Consent]) -> bool:
        consent = current.get(HEALTH_DATA)
        return consent is not None and consent.active

    # ── writes ────────────────────────────────────────────────────────────────

    def accept(self, userId: str, documents: list[str]) -> list[Consent]:
        """Record agreement to one or more documents at their current version.

        The version is stamped here and never taken from the caller. A client
        that could name the version it was agreeing to could record an
        agreement to a text it never displayed, which is the one thing a
        consent record must not be able to say.

        Accepting something already accepted at the same version writes another
        row rather than erroring. Two taps on a slow connection are one
        intention, and refusing the second would put the app in front of a gate
        it has already passed.
        """
        unknown = [document for document in documents if document not in DOCUMENTS]
        if unknown:
            raise NoHarmException(
                statusCode=400,
                errorCode="UNKNOWN_DOCUMENT",
                message="Unknown document."
            )

        if not documents:
            raise NoHarmException(
                statusCode=400,
                errorCode="NOTHING_TO_ACCEPT",
                message="No documents given."
            )

        # De-duplicated, and in DOCUMENTS order so the rows read the same way
        # every time regardless of what order the client listed them in.
        wanted = [document for document in DOCUMENTS if document in set(documents)]
        now = _utcNow()

        recorded = self.consentRepository.createMany([
            Consent(
                user_id=userId,
                document=document,
                version=self.currentVersion(document),
                accepted_at=now
            )
            for document in wanted
        ])

        for consent in recorded:
            self._logAudit(
                _AUDIT_CONSENT_GIVEN,
                userId,
                f"Consent given: {consent.document} v{consent.version}"
            )

        return recorded

    def recordRegistrationConsents(self, userId: str, healthData: bool) -> list[Consent]:
        """The three rows an account starts life with, in one commit.

        Called from `AuthService.register`, which has already refused the
        request if the terms and privacy policy were not accepted — so this
        does not re-check them. `healthData` is the only genuinely optional one
        and is simply absent when declined.
        """
        documents = [TERMS, PRIVACY] + ([HEALTH_DATA] if healthData else [])
        return self.accept(userId, documents)

    def withdrawHealthData(self, userId: str) -> dict:
        """Take back consent to hold recovery data, and delete what it covered.

        Withdrawal that leaves the data in place is not withdrawal, so the
        streaks go — every one of them, including the closed ones that make up
        the history and the personal record. That is the honest reading of
        "stop holding my health data", and it is destructive in a way nothing
        else in the app is: there is no grace window and no undo, because a
        30-day shadow copy of data someone asked to be rid of is the thing they
        asked to be rid of.

        The consent record itself survives, stamped with the moment it ended.
        It is the only evidence the withdrawal was honoured, and deleting it
        would leave the account unable to show that it ever asked.

        Idempotent: withdrawing when nothing is in force deletes nothing and
        reports `withdrawn: False`.
        """
        consent = self.consentRepository.withdraw(userId, HEALTH_DATA)

        if consent is None:
            return {"withdrawn": False, "streaksDeleted": 0}

        # Read the ids first. Deleting from a list being iterated out of the
        # same session is the kind of thing that works until the day the
        # repository starts returning a lazy result.
        streaks = self.streakRepository.findAllByOwnerId(userId)
        streakIds = [str(streak.id) for streak in streaks]

        deleted = 0
        for streakId in streakIds:
            # One failure must not strand the rest: a partial delete is bad,
            # and a partial delete that stopped at the first error is worse.
            try:
                self.streakRepository.delete(streakId)
                deleted += 1
            except Exception:
                continue

        self._logAudit(
            _AUDIT_CONSENT_WITHDRAWN,
            userId,
            f"Consent withdrawn: {HEALTH_DATA} v{consent.version}; {deleted} streak(s) deleted"
        )

        return {"withdrawn": True, "streaksDeleted": deleted}
