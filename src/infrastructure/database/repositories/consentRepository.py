from domain.entities.consent import Consent
from core.errorUtils import excLocation
from infrastructure.database.models.consentModel import ConsentModel
from infrastructure.database.models.userModel import UserModel
from exceptions.baseExceptions import NoHarmException

from core.config import config
from core.database import Database

from sqlalchemy import or_, select

from datetime import datetime, timezone
from typing import Optional


def _utcNow() -> datetime:
    """Now, as the naive UTC the schema stores."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ConsentRepository:
    """Reads and writes `tb_13`. Append-only, apart from withdrawal.

    Nothing here updates a consent's document or version, and nothing deletes a
    row. Agreeing again writes a new row; taking it back stamps `cl_13f` on the
    row that is current. Both are facts about the past, and the past is not
    edited.
    """

    def __init__(self, db: Database):
        self.db = db
        self.session = self.db.session
        self.engine = self.db.engine


    def _toEntity(self, model: ConsentModel) -> Consent:
        return Consent(
            id=model.id,
            user_id=model.user_id,
            document=model.document,
            version=model.version,
            accepted_at=model.accepted_at,
            withdrawn_at=model.withdrawn_at,
            created_at=model.created_at,
            updated_at=model.updated_at
        )


    def create(self, consent: Consent) -> Consent:
        """Record one agreement.

        Commits on its own, like every other repository here. Registration is
        the one caller that would rather it did not — three consents and a user
        row want to land together — and `createMany` is what it uses instead.
        """
        try:
            model = ConsentModel(
                user_id=consent.user_id,
                document=consent.document,
                version=consent.version,
                accepted_at=consent.accepted_at or _utcNow()
            )

            self.session.add(model)
            self.session.commit()

            return self._toEntity(model)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def createMany(self, consents: list[Consent]) -> list[Consent]:
        """Record several agreements in one commit.

        One transaction because the set is the point: an account that recorded
        its agreement to the terms but not to the privacy policy, because the
        second insert failed, is an account the consent gate will stop at its
        next launch — with no way for the user to tell what went wrong.
        """
        if not consents:
            return []

        try:
            models = [
                ConsentModel(
                    user_id=consent.user_id,
                    document=consent.document,
                    version=consent.version,
                    accepted_at=consent.accepted_at or _utcNow()
                )
                for consent in consents
            ]

            self.session.add_all(models)
            self.session.commit()

            return [self._toEntity(model) for model in models]
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def findByUser(self, userId: str) -> list[Consent]:
        """Every consent this account ever gave, oldest first.

        The whole history, withdrawn rows included — it is what the data export
        carries, and an export that showed only what is currently in force
        would be answering a different question than the one asked.
        """
        try:
            models = self.session.query(ConsentModel).filter(
                ConsentModel.user_id == userId
            ).order_by(ConsentModel.accepted_at.asc(), ConsentModel.id.asc()).all()

            return [self._toEntity(model) for model in models]
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def countOwingReacceptance(self, currentVersions: dict[str, str]) -> dict[str, int]:
        """How many **accounts** owe an answer, per document and in total.

        The global form of `ConsentService._pending`, and the one query on this
        board that cannot be a `GROUP BY`. Three states count as owing, and
        only the first is visible in `tb_13` at all:

        - the newest row for that document is at an old version;
        - the newest row is withdrawn;
        - there is no row — an account that predates the document, which is
          exactly the population a newly published policy is aimed at.

        The third is why this starts from `tb_0` and joins outwards. A query
        over `tb_13` alone answers "whose stored consent is stale" and silently
        reports zero for every account that never had one.

        `DISTINCT ON (user_id, document)` picks the newest row per pair, with
        the primary key breaking ties for the same reason `findCurrent` does:
        registration writes three rows in one transaction and their timestamps
        can be equal to the microsecond.

        Only `enabled` accounts are counted. A deleted or banned account does
        not owe anything — it cannot reach the gate to answer, and including it
        would make the number grow every time someone leaves.

        Returns `{document: accounts, "any": accountsOwingAtLeastOne}`. `any`
        is not the sum: one account behind on both documents is one account,
        and a board that added them up would report more work than exists.
        """
        if not currentVersions:
            return {"any": 0}

        try:
            documents = list(currentVersions)

            # The newest row per (user, document) — withdrawn ones included,
            # because "withdrawn yesterday" is a state this has to see.
            newest = (
                select(
                    ConsentModel.user_id.label("user_id"),
                    ConsentModel.document.label("document"),
                    ConsentModel.version.label("version"),
                    ConsentModel.withdrawn_at.label("withdrawn_at"),
                )
                .distinct(ConsentModel.user_id, ConsentModel.document)
                .where(ConsentModel.document.in_(documents))
                .order_by(
                    ConsentModel.user_id,
                    ConsentModel.document,
                    ConsentModel.accepted_at.desc(),
                    ConsentModel.id.desc(),
                )
                .subquery()
            )

            counts: dict[str, int] = {}
            owing_users: set[str] = set()

            for document, version in currentVersions.items():
                rows = (
                    self.session.query(UserModel.id)
                    .outerjoin(
                        newest,
                        (newest.c.user_id == UserModel.id)
                        & (newest.c.document == document),
                    )
                    .filter(UserModel.status == config.STATUS_CODES["enabled"])
                    .filter(
                        or_(
                            newest.c.user_id.is_(None),          # never answered
                            newest.c.withdrawn_at.isnot(None),   # taken back
                            newest.c.version != version,         # answered an older text
                        )
                    )
                    .all()
                )
                ids = {row[0] for row in rows}
                counts[document] = len(ids)
                owing_users |= ids

            counts["any"] = len(owing_users)
            return counts
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')

    def findCurrent(self, userId: str) -> dict[str, Consent]:
        """The newest consent per document, keyed by document.

        Newest by `accepted_at`, with the primary key breaking ties: two rows
        written in the same transaction — which registration does — carry
        timestamps that can be equal to the microsecond.

        A withdrawn row can be the current one. That is deliberate: "withdrawn
        yesterday" and "never given" are different states and the caller has to
        be able to tell them apart.
        """
        try:
            models = self.session.query(ConsentModel).filter(
                ConsentModel.user_id == userId
            ).order_by(ConsentModel.accepted_at.asc(), ConsentModel.id.asc()).all()

            # Later rows overwrite earlier ones, so the last write per document
            # wins — the same order the query already returns.
            current: dict[str, Consent] = {}
            for model in models:
                current[model.document] = self._toEntity(model)

            return current
        except Exception as e:
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')


    def withdraw(self, userId: str, document: str) -> Optional[Consent]:
        """Stamp the account's current consent for one document as withdrawn.

        Returns None when there is nothing in force to withdraw — never given,
        or already withdrawn. Idempotent for the same reason acknowledging a
        notice is: the first withdrawal is the one that counts, and a second
        call must not move the date.
        """
        try:
            model = self.session.query(ConsentModel).filter(
                ConsentModel.user_id == userId,
                ConsentModel.document == document,
                ConsentModel.withdrawn_at.is_(None)
            ).order_by(ConsentModel.accepted_at.desc(), ConsentModel.id.desc()).first()

            if model is None:
                return None

            model.withdrawn_at = _utcNow()
            self.session.commit()

            return self._toEntity(model)
        except Exception as e:
            self.session.rollback()
            if isinstance(e, NoHarmException):
                raise e
            raise NoHarmException(statusCode=500, message=f'{type(e).__name__}: {e} in {excLocation()}')
