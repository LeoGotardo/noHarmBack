"""moderation notices: tb_12

Revision ID: 20260911_04
Revises: 20260911_03
Create Date: 2026-09-11

Moderation could do two things to an account — nothing, or ban it — and this
adds the one in between: telling the person. Until now a moderator who agreed
with a report but did not think it deserved a suspension had no way to say so,
so the ladder in the policy jumped from silence straight to losing the account,
and in practice the answer to almost everything was silence.

`tb_12` is one row per thing moderation said to a user:

- `warning` — nothing about the account changed. Someone looked, agreed, and is
  saying it once.
- `suspension` — written beside the ban, so an account that comes back after
  three days is not left guessing what happened.

## What a notice must not contain

Who reported them. A notice names the **conduct** (`cl_12d`, the same reason
codes a report uses) and optionally the moderator's own words (`cl_12e`,
encrypted like a report's details, because it is prose about a person). The
promise that a reported user is never told who complained is the whole reason
reports get filed at all, and a warning that leaks the complainant turns every
report into a confrontation between two users.

`self_harm` is deliberately absent from the codes a warning may carry — that
report is usually a frightened friend, and `NoticeService.warn` refuses it with
the reason spelled out.

## Acknowledgement

`cl_12g` is when the user tapped "I understand". Unacknowledged notices are what
the app shows on open; an acknowledged one is history and stays on file.
Acknowledging is not agreeing: appeals go to support, and the notice is kept
either way so a second moderator reviewing an appeal can see what was said.

## RLS

A user reads and acknowledges their own notices and nothing else. Only a session
with no context — the admin routes' `getDb` — can write one, so a notice cannot
be self-issued or forged by the account it is about. No DELETE policy at all:
what moderation told someone is not something moderation gets to unsay.
"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


revision = "20260911_04"
down_revision = "20260911_03"
branch_labels = None
depends_on = None


_POLICIES = [
    ("tb_12_select_own", "SELECT",
     "app_current_user_id() IS NULL OR cl_12b = app_current_user_id()", None),
    # Moderation writes; nobody writes their own.
    ("tb_12_insert_admin", "INSERT", None, "app_current_user_id() IS NULL"),
    # The recipient may acknowledge; the WITH CHECK keeps the row theirs.
    ("tb_12_update_own", "UPDATE",
     "app_current_user_id() IS NULL OR cl_12b = app_current_user_id()",
     "app_current_user_id() IS NULL OR cl_12b = app_current_user_id()"),
]


def upgrade() -> None:
    op.create_table(
        "tb_12",
        sa.Column("cl_12a", sa.UUID(), nullable=False),
        sa.Column("cl_12b", sa.String(), nullable=False),
        sa.Column("cl_12c", sa.String(length=16), nullable=False),
        sa.Column("cl_12d", sa.String(length=32), nullable=False),
        sa.Column("cl_12e", sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(), nullable=True),
        sa.Column("cl_12f", sa.String(), nullable=True),
        sa.Column("cl_12g", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cl_12b"], ["tb_0.cl_0a"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cl_12a"),
    )

    # cl_12b carries the RLS predicate and every read the app makes ("what is
    # waiting for me"), so it would be a sequential scan without this.
    op.execute("CREATE INDEX IF NOT EXISTS ix_tb_12_cl_12b ON tb_12 (cl_12b)")

    op.execute("ALTER TABLE tb_12 ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_12 FORCE ROW LEVEL SECURITY")

    for name, command, using, check in _POLICIES:
        sql = f"CREATE POLICY {name} ON tb_12 FOR {command} TO PUBLIC"
        if using is not None:
            sql += f" USING ({using})"
        if check is not None:
            sql += f" WITH CHECK ({check})"
        op.execute(sql)


def downgrade() -> None:
    for name, _, _, _ in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON tb_12")

    op.execute("ALTER TABLE tb_12 NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_12 DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_tb_12_cl_12b")

    op.drop_table("tb_12")
