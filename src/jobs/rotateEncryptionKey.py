"""Re-encrypt every encrypted column from an old key to the current one.

Run as a one-shot task, with the app stopped:

    DATABASE_ENCRYPTION_KEY_OLD=<old> DATABASE_ENCRYPTION_KEY=<new> \
        docker compose run --rm app rotate-encryption-key [--dry-run]

The runbook — stop, back up, rotate, start with the new key — is in
`docs/operations.md`, "Rotating the column encryption key".

What it touches: every column declared as `StringEncryptedType`, found from the
models' metadata, so a table added later is covered without editing this file.
Ciphertext is rewritten at the string level — decrypt with the old engine,
encrypt with the new — so no value passes through its Python type and nothing
about it can change except the key.

What it does not touch: `BLIND_INDEX_KEY`. The lookup indexes are HMACs under a
separate key; rotating that one is migration `20260902_01`.

**Resumable.** A value that already decrypts under the new key is skipped, so a
run that died halfway is finished by running it again. A value that decrypts
under neither key is reported and the run fails without writing that table:
it is either corrupt or encrypted under a third key, and either way the person
rotating needs to know before the old key is thrown away.

It connects with `DATABASE_URL_UNPOOLED` — the owner role — because several
tables (the audit log, report evidence) have no UPDATE policy for the
application role at all.

Exit codes: 0 when every value is under the new key (or would be, with
`--dry-run`), 1 otherwise.
"""
import logging
import os
import sys

from sqlalchemy import Text, and_, create_engine, or_, select, type_coerce, update
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine, InvalidCiphertextError

from core.config import config
import infrastructure.database.models  # noqa: F401 — registers every table
from infrastructure.external.storageService import Base

logger = logging.getLogger("noharm.rotateKey")

_BATCH = 500


def _engine(key: str) -> AesGcmEngine:
    engine = AesGcmEngine()
    engine._update_key(key)  # SHA-256 of the key, exactly as StringEncryptedType does
    return engine


def _decrypts(engine: AesGcmEngine, value: str) -> bool:
    try:
        engine.decrypt(value)
        return True
    except (InvalidCiphertextError, ValueError):
        return False


def encryptedColumns() -> dict:
    """{table: [encrypted column, ...]} for every table that has any."""
    found = {}
    for table in Base.metadata.sorted_tables:
        columns = [c for c in table.columns if isinstance(c.type, StringEncryptedType)]
        if columns:
            found[table] = columns
    return found


def rotate(connection, oldKey: str, newKey: str, dryRun: bool = False) -> dict:
    """Rotate every table. Returns {"rewritten", "already", "undecryptable"} counts."""
    old, new = _engine(oldKey), _engine(newKey)
    totals = {"rewritten": 0, "already": 0, "undecryptable": 0}

    for table, columns in encryptedColumns().items():
        pk = list(table.primary_key.columns)
        # `type_coerce(..., Text)` on both sides: through the column's own type
        # SQLAlchemy would decrypt on the way out and encrypt again on the way
        # in. This job has to see and write the ciphertext itself.
        raw = {c.name: type_coerce(c, Text).label(c.name) for c in columns}
        query = select(*pk, *raw.values()).where(or_(*[c.isnot(None) for c in columns]))

        changes = []  # (pk values, {column: new ciphertext})
        bad = 0
        for row in connection.execute(query).mappings():
            newValues = {}
            for column in columns:
                value = row[column.name]
                if value is None:
                    continue
                if _decrypts(new, value):
                    totals["already"] += 1
                    continue
                try:
                    newValues[column.name] = new.encrypt(old.decrypt(value))
                except (InvalidCiphertextError, ValueError):
                    bad += 1
            if newValues:
                changes.append(([row[c.name] for c in pk], newValues))

        if bad:
            totals["undecryptable"] += bad
            logger.error("%s: %s value(s) decrypt under neither key — table left untouched", table.name, bad)
            continue

        if not dryRun:
            for start in range(0, len(changes), _BATCH):
                for pkValues, newValues in changes[start:start + _BATCH]:
                    condition = and_(*[c == v for c, v in zip(pk, pkValues)])
                    connection.execute(
                        update(table).where(condition).values(
                            {table.c[name]: type_coerce(value, Text) for name, value in newValues.items()}
                        )
                    )
                connection.commit()

        rewritten = sum(len(v) for _, v in changes)
        totals["rewritten"] += rewritten
        if rewritten:
            logger.info("%s: %s %s value(s)", table.name, "would rewrite" if dryRun else "rewrote", rewritten)

    return totals


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [rotate-encryption-key] %(levelname)s %(message)s",
    )
    argv = sys.argv[1:] if argv is None else argv
    dryRun = "--dry-run" in argv

    oldKey = os.environ.get("DATABASE_ENCRYPTION_KEY_OLD")
    newKey = config.DATABASE_ENCRYPTION_KEY
    if not oldKey:
        logger.error("DATABASE_ENCRYPTION_KEY_OLD is not set — nothing to rotate from")
        return 1
    if oldKey == newKey:
        logger.error("the old and new keys are identical — set DATABASE_ENCRYPTION_KEY to the new key")
        return 1

    try:
        engine = create_engine(config.DATABASE_URL_UNPOOLED)
        with engine.connect() as connection:
            totals = rotate(connection, oldKey, newKey, dryRun=dryRun)
    except Exception:
        logger.exception("rotation aborted")
        return 1

    logger.info(
        "%s: %s rewritten, %s already under the new key, %s undecryptable",
        "dry run" if dryRun else "done",
        totals["rewritten"], totals["already"], totals["undecryptable"],
    )
    return 1 if totals["undecryptable"] else 0


if __name__ == "__main__":
    sys.exit(main())
