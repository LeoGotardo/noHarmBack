"""re-key the blind indexes from bare SHA-256 to HMAC-SHA256

Revision ID: 20260902_01
Revises: 20260901_01
Create Date: 2026-09-02

`username`, `email` and `device_fcm` are stored encrypted, and each carries a
sibling column holding a digest of the plaintext so that an exact-match lookup
is still possible: `cl_0b_h`, `cl_0c_h`, `cl_9c_h`.

Those digests were `sha256(value)` with no key. That made the index strictly
weaker than the ciphertext beside it — anyone who could read the table could
recover every e-mail with a wordlist and every username by enumerating
`^[a-zA-Z0-9_-]{3,30}$`, without ever touching DATABASE_ENCRYPTION_KEY. The
encryption on the columns was, for those three values, decorative.

`Encryption.hash` is now HMAC-SHA256 under BLIND_INDEX_KEY. This migration
rewrites the stored indexes to match. It has to: the lookups compare a freshly
computed index against a stored one, so until every row is rewritten, sign-in by
e-mail, username search and FCM token de-duplication all miss and behave exactly
like "no such user".

Reads go through StringEncryptedType, so SQLAlchemy decrypts each value with
DATABASE_ENCRYPTION_KEY, and the new index is computed from the plaintext. Both
keys must therefore be present and correct when this runs — a wrong
DATABASE_ENCRYPTION_KEY raises on the first row rather than writing garbage.

Rows are streamed in batches: the tables are small today, but loading an entire
user table into memory to hash it is not a thing that ages well.

The downgrade recomputes the unkeyed digests, restoring the weaker index. It
exists so the migration is reversible in the ordinary sense, not because
reverting is advisable.

Rotating BLIND_INDEX_KEY later is this same operation: set the new key and run
`alembic downgrade`/`upgrade` across this revision, or re-run the upgrade body
with both keys in hand.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine

from hashlib import sha256
import hmac

from core.config import config as appConfig


revision = "20260902_01"
down_revision = "20260901_01"
branch_labels = None
depends_on = None


_BATCH = 500


# (table, id column, encrypted column, index column) — must match
# userModel.UserModel and notificationModel.NotificationModel exactly. A column
# type that differs from the model's does not error, it silently decrypts to
# nonsense, so these are spelled out rather than reflected.
_INDEXED_COLUMNS = [
    ("tb_0", "cl_0a", sa.String,  "cl_0b", "cl_0b_h"),  # users.username
    ("tb_0", "cl_0a", sa.String,  "cl_0c", "cl_0c_h"),  # users.email
    ("tb_9", "cl_9a", UUID(as_uuid=True), "cl_9c", "cl_9c_h"),  # notifications.device_fcm
]


def _table(name: str, idColumn: str, idType, valueColumn: str, indexColumn: str) -> sa.Table:
    key = appConfig.DATABASE_ENCRYPTION_KEY
    return sa.table(
        name,
        sa.column(idColumn, idType),
        sa.column(valueColumn, StringEncryptedType(sa.Text, key, AesGcmEngine, "pkcs5")),
        sa.column(indexColumn, sa.String(64)),
    )


def _rehash(indexOf) -> None:
    """Recompute every blind index with `indexOf`, in batches."""
    connection = op.get_bind()

    for name, idColumn, idType, valueColumn, indexColumn in _INDEXED_COLUMNS:
        table = _table(name, idColumn, idType, valueColumn, indexColumn)
        idCol = table.c[idColumn]
        valueCol = table.c[valueColumn]

        # Keyset pagination on the primary key. OFFSET would drift here: the
        # UPDATE below does not change the ordering column, but a concurrent
        # insert would, and re-reading a shifted window silently skips rows.
        lastId = None
        while True:
            query = sa.select(idCol, valueCol).order_by(idCol).limit(_BATCH)
            if lastId is not None:
                query = query.where(idCol > lastId)

            rows = connection.execute(query).fetchall()
            if not rows:
                break

            for rowId, value in rows:
                if value is None:
                    continue
                connection.execute(
                    table.update()
                    .where(idCol == rowId)
                    .values(**{indexColumn: indexOf(value)})
                )

            lastId = rows[-1][0]


def upgrade() -> None:
    key = appConfig.BLIND_INDEX_KEY.encode("utf-8")
    _rehash(lambda value: hmac.new(key, value.encode("utf-8"), sha256).hexdigest())


def downgrade() -> None:
    _rehash(lambda value: sha256(value.encode("utf-8")).hexdigest())
