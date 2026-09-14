"""report evidence (tb_11), and reports that outlive the account they name

Revision ID: 20260911_01
Revises: 20260909_01
Create Date: 2026-09-11

A report used to be one sentence of prose and a reason code. Acting on it meant
believing one of two strangers, and the only person who could say what actually
happened was the one being accused. This adds the two things that were missing
and nothing else: a copy of what the report is about, and a report that does not
vanish with the account it accuses.

## tb_11 — the copy

One row per captured item: the reported profile as it was that day, and the tail
of the conversation when the report named one. Three properties:

- **It is a copy, not a reference.** `cl_11d` (the source row) and `cl_11e` (its
  author) are plain strings with no foreign key. The day the reported account is
  purged is precisely the day the evidence about it matters most, and a foreign
  key would take it with the account.
- **The server writes it.** The request body carries a chat id; `ReportService`
  copies the message bodies out of `tb_4`. Nothing the reporter types lands
  here, or the feature is a text box for putting words in someone's mouth.
- **It is tamper-evident.** `cl_11g` is `Encryption.hash` of the plaintext — the
  keyed blind index, not a bare digest — so a row edited afterwards no longer
  matches its own hash. The content itself is encrypted like a message body,
  because that is mostly what it is.

`created_at` is when the capture happened; `cl_11h` is when the captured thing
was said. A moderator needs both, and they are not the same question.

## tb_10 — surviving the purge

`cl_10c` was ON DELETE CASCADE, which made deleting your account a way to erase
every open complaint about you: wait out the 30-day grace window and the queue
forgets. It becomes ON DELETE SET NULL, and two copies take over what the key
used to answer — `cl_10g`, the reported user's id at filing time, and `cl_10h`,
their username then. Both are snapshots, so `findOpenByPair` and
`countByReported` keep working against an account that no longer exists.

The reporter's side is deliberately *not* copied. `cl_10b` stays a plain SET
NULL: a purged reporter becomes anonymous, and that asymmetry is the point —
the evidence is about the reported user's conduct, and nobody's identity needs
to survive their own deletion for a moderator to judge it.

## RLS

`tb_11` is admin-only to read: a session with no `app_current_user_id()`, which
is what `getDb` gives the admin routes. The reporter may INSERT rows for their
own report — capture runs on their request — and that is all they may do. No
UPDATE policy at all, so nothing rewrites a capture; DELETE is context-free
only, which is the retention job (`jobs/purgeEvidence.py`) and nothing reachable
from a request.
"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


revision = "20260911_01"
down_revision = "20260909_01"
branch_labels = None
depends_on = None


_POLICIES = [
    # Admin reads. The reporter does not read back what was captured: they saw
    # the conversation already, and the copy exists for moderation, not for them.
    ("tb_11_select_admin", "SELECT", "app_current_user_id() IS NULL", None),
    # Capture happens inside POST /reports, on the reporter's own session.
    ("tb_11_insert_own_report", "INSERT", None,
     "app_current_user_id() IS NULL OR EXISTS ("
     "  SELECT 1 FROM tb_10 WHERE tb_10.cl_10a = tb_11.cl_11b"
     "     AND tb_10.cl_10b = app_current_user_id())"),
    # Retention only, from a job. No UPDATE policy exists, which is what makes
    # a captured row append-only.
    ("tb_11_delete_admin", "DELETE", "app_current_user_id() IS NULL", None),
]


def upgrade() -> None:
    # ── tb_10: the report outlives the reported account ────────────────────
    op.add_column("tb_10", sa.Column("cl_10g", sa.String(), nullable=True))
    op.add_column("tb_10", sa.Column("cl_10h", sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(), nullable=True))

    # Existing rows still have their foreign key, so the snapshot is simply the
    # value it points at. The username is left NULL rather than decrypted and
    # re-encrypted here: a moderator reading an old report can still resolve it
    # through cl_10c, which for those rows is by definition still there.
    op.execute("UPDATE tb_10 SET cl_10g = cl_10c WHERE cl_10g IS NULL")
    op.alter_column("tb_10", "cl_10g", nullable=False)

    op.drop_constraint("tb_10_cl_10c_fkey", "tb_10", type_="foreignkey")
    op.alter_column("tb_10", "cl_10c", nullable=True)
    op.create_foreign_key(
        "tb_10_cl_10c_fkey", "tb_10", "tb_0", ["cl_10c"], ["cl_0a"], ondelete="SET NULL"
    )

    # Every moderation lookup moved off the foreign key and onto the snapshot.
    op.execute("CREATE INDEX IF NOT EXISTS ix_tb_10_cl_10g ON tb_10 (cl_10g)")

    # ── tb_11: the evidence ────────────────────────────────────────────────
    op.create_table(
        "tb_11",
        sa.Column("cl_11a", sa.UUID(), nullable=False),
        sa.Column("cl_11b", sa.UUID(), nullable=False),
        sa.Column("cl_11c", sa.String(length=16), nullable=False),
        sa.Column("cl_11d", sa.String(), nullable=True),
        sa.Column("cl_11e", sa.String(), nullable=True),
        sa.Column("cl_11f", sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(), nullable=False),
        sa.Column("cl_11g", sa.String(length=64), nullable=False),
        sa.Column("cl_11h", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cl_11b"], ["tb_10.cl_10a"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cl_11a"),
    )

    # cl_11b carries both the RLS predicate and every read: evidence is always
    # fetched for one report.
    op.execute("CREATE INDEX IF NOT EXISTS ix_tb_11_cl_11b ON tb_11 (cl_11b)")

    op.execute("ALTER TABLE tb_11 ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_11 FORCE ROW LEVEL SECURITY")

    for name, command, using, check in _POLICIES:
        sql = f"CREATE POLICY {name} ON tb_11 FOR {command} TO PUBLIC"
        if using is not None:
            sql += f" USING ({using})"
        if check is not None:
            sql += f" WITH CHECK ({check})"
        op.execute(sql)


def downgrade() -> None:
    for name, _, _, _ in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON tb_11")

    op.execute("ALTER TABLE tb_11 NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_11 DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_tb_11_cl_11b")
    op.drop_table("tb_11")

    op.execute("DROP INDEX IF EXISTS ix_tb_10_cl_10g")

    # Going back means the cascade returns, so any report whose account was
    # already purged has to go first — its cl_10c is NULL and cannot be made
    # NOT NULL again.
    op.execute("DELETE FROM tb_10 WHERE cl_10c IS NULL")
    op.drop_constraint("tb_10_cl_10c_fkey", "tb_10", type_="foreignkey")
    op.alter_column("tb_10", "cl_10c", nullable=False)
    op.create_foreign_key(
        "tb_10_cl_10c_fkey", "tb_10", "tb_0", ["cl_10c"], ["cl_0a"], ondelete="CASCADE"
    )

    op.drop_column("tb_10", "cl_10h")
    op.drop_column("tb_10", "cl_10g")
