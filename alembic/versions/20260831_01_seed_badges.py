"""seed the badge catalogue

Revision ID: 20260831_01
Revises: 20260812_01
Create Date: 2026-08-31

tb_5 has never been populated, and 20260812_01 reset every milestone it might
have held to 0 — so on a fresh database `GET /badges` returns an empty list and
`grantMilestoneBadges` has nothing to grant no matter how long a streak runs.
The badges screen renders, empty, forever.

The rows are keyed on `milestone`, which is the only column not encrypted and
therefore the only one that can be matched in SQL: name, description and icon
go through StringEncryptedType with a per-deployment key, so two rows with the
same name have different ciphertext and `WHERE name = ...` can never work.

Idempotent: a milestone already present is left exactly as it is, including any
edit made to its text. Re-running this on a seeded database changes nothing.

The downgrade removes only the milestones this file introduced, and only while
no user holds them — a badge someone earned is a fact about their recovery, and
dropping it to satisfy a schema rollback is not a trade worth making.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy_utils import StringEncryptedType
from sqlalchemy_utils.types.encrypted.encrypted_type import AesGcmEngine

from datetime import datetime, timezone
import uuid

from core.config import config as appConfig


revision = "20260831_01"
down_revision = "20260812_01"
branch_labels = None
depends_on = None


# Must match badgeModel.BadgeModel exactly — same columns, same engine, same
# key. A mismatch does not error: it writes ciphertext the application cannot
# read back, and the badge screen fills with decryption failures.
def _badgeTable() -> sa.Table:
    key = appConfig.DATABASE_ENCRYPTION_KEY
    encrypted = lambda: StringEncryptedType(sa.Text, key, AesGcmEngine, "pkcs5")

    return sa.table(
        "tb_5",
        sa.column("cl_5a", UUID(as_uuid=True)),
        sa.column("cl_5b", encrypted()),  # name
        sa.column("cl_5c", encrypted()),  # description
        sa.column("cl_5d", sa.Integer),   # milestone, in clean days
        sa.column("cl_5e", encrypted()),  # icon
        sa.column("cl_5f", sa.Integer),   # status
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )


# (milestone days, name, description, icon)
#
# The ladder is dense in the first week and thins out after: the days that are
# hardest to survive are the ones worth marking, and a first badge that takes a
# month to reach is a first badge nobody sees. Copy is second person and warm —
# it is read by someone who just got through a day that was hard.
BADGES = [
    (1, "First Day", "You made it through day one. This is the hardest one there is.", "sunrise"),
    (3, "Three Days", "Three days clean. The fog starts to lift around here.", "leaf"),
    (7, "One Week", "A full week. You've proven this is something you can do.", "star"),
    (14, "Two Weeks", "Fourteen days. The new routine is starting to hold on its own.", "shield"),
    (30, "One Month", "A month clean. Look back at where you were thirty days ago.", "moon"),
    (60, "Two Months", "Sixty days. This is no longer a streak — it's how you live.", "flame"),
    (90, "Ninety Days", "Ninety days, the milestone every recovery programme marks. You're there.", "trophy"),
    (180, "Six Months", "Half a year. Most of the people who reach this never look back.", "mountain"),
    (270, "Nine Months", "Two hundred and seventy days of choosing this, one day at a time.", "compass"),
    (365, "One Year", "A whole year clean. Whatever you tell yourself, this is extraordinary.", "crown"),
]

# STATUS_CODES.enabled — the value the app filters on. Read from config rather
# than written as 1 so that a deployment which renumbered its status table
# still seeds rows its own queries can see.
_ENABLED = int(appConfig.STATUS_CODES["enabled"])


def upgrade() -> None:
    connection = op.get_bind()
    table = _badgeTable()

    existing = {
        row[0]
        for row in connection.execute(sa.text("SELECT cl_5d FROM tb_5")).fetchall()
    }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        {
            "cl_5a": uuid.uuid4(),
            "cl_5b": name,
            "cl_5c": description,
            "cl_5d": milestone,
            "cl_5e": icon,
            "cl_5f": _ENABLED,
            "created_at": now,
            "updated_at": now,
        }
        for milestone, name, description, icon in BADGES
        if milestone not in existing
    ]

    if rows:
        connection.execute(table.insert(), rows)


def downgrade() -> None:
    connection = op.get_bind()
    milestones = [milestone for milestone, _, _, _ in BADGES]

    # tb_6 is the user↔badge join. A badge referenced there stays.
    connection.execute(
        sa.text(
            """
            DELETE FROM tb_5
             WHERE cl_5d = ANY(:milestones)
               AND cl_5a NOT IN (SELECT cl_6c FROM tb_6)
            """
        ),
        {"milestones": milestones},
    )
