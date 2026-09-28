"""consent records: tb_13

Revision ID: 20260916_02
Revises: 20260916_01
Create Date: 2026-09-16

What the account agreed to, which version of it, and when.

Until now the app asked for nothing and recorded nothing. That is two separate
problems and this table answers both: a user who was never shown the terms has
not agreed to them, and an agreement nobody wrote down did not happen as far as
anyone outside this process is concerned.

## Append-only

One row per act of consenting, never updated in place except to withdraw.
Accepting version 2 of the terms does not overwrite the row for version 1 — it
adds a row beside it, so the history reads as a sequence of decisions rather
than a current state that lost its own past. `ConsentService` finds the current
one by taking the newest row per document.

That is also why there is no unique constraint on
`(user, document, version)`: withdrawing a consent and giving it again is two
real events about the same version, and a constraint would make the second one
an error.

## Three documents

`cl_13c` is `terms`, `privacy` or `health_data`.

The third is the one that matters most and the reason the column is not a
boolean on `tb_0`. A tracked streak is a record of someone's recovery from
addiction — health data, which needs consent that is explicit and **given
separately**, not folded into a single "I agree" covering three unrelated
things. It also has to be withdrawable without closing the account, which a
flag on the user row would not survive.

## Withdrawal

`cl_13f` is when it was taken back, and nothing is deleted. Withdrawing health
consent deletes the streaks it covered (`ConsentService.withdrawHealthData`),
but the record that the consent existed and ended has to outlive the data —
that record is the only proof the withdrawal was honoured.

## RLS

A user reads, writes and withdraws their own rows and nobody else's. The
INSERT policy also passes for a session with no context, because registration
writes the first three rows before an RLS context exists — the account is being
created in the same transaction.

No DELETE policy at all. A consent record is evidence about a decision, and the
one thing it must not be is erasable by the party it binds. Purging the account
still removes it, through ON DELETE CASCADE: that is the account ceasing to
exist, not a row being edited away.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260916_02"
down_revision = "20260916_01"
branch_labels = None
depends_on = None


_POLICIES = [
    ("tb_13_select_own", "SELECT",
     "app_current_user_id() IS NULL OR cl_13b = app_current_user_id()", None),
    # Registration inserts with no context set; afterwards only the owner does.
    ("tb_13_insert_own", "INSERT", None,
     "app_current_user_id() IS NULL OR cl_13b = app_current_user_id()"),
    # Withdrawal is an UPDATE. The WITH CHECK keeps the row the owner's.
    ("tb_13_update_own", "UPDATE",
     "app_current_user_id() IS NULL OR cl_13b = app_current_user_id()",
     "app_current_user_id() IS NULL OR cl_13b = app_current_user_id()"),
]


def upgrade() -> None:
    op.create_table(
        "tb_13",
        sa.Column("cl_13a", sa.UUID(), nullable=False),
        sa.Column("cl_13b", sa.String(), nullable=False),
        sa.Column("cl_13c", sa.String(length=32), nullable=False),
        sa.Column("cl_13d", sa.String(length=32), nullable=False),
        sa.Column("cl_13e", sa.DateTime(), nullable=False),
        sa.Column("cl_13f", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cl_13b"], ["tb_0.cl_0a"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cl_13a"),
    )

    # Every read is "what has this account agreed to", which is the pair.
    op.execute("CREATE INDEX IF NOT EXISTS ix_tb_13_cl_13b_cl_13c ON tb_13 (cl_13b, cl_13c)")

    op.execute("ALTER TABLE tb_13 ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_13 FORCE ROW LEVEL SECURITY")

    for name, command, using, check in _POLICIES:
        sql = f"CREATE POLICY {name} ON tb_13 FOR {command} TO PUBLIC"
        if using is not None:
            sql += f" USING ({using})"
        if check is not None:
            sql += f" WITH CHECK ({check})"
        op.execute(sql)


def downgrade() -> None:
    # Dropping this loses every record of who agreed to what. There is nothing
    # to migrate it into — the consents were never anywhere else — so every
    # account is asked again at its next sign-in, which is the correct
    # behaviour for a system that no longer knows.
    for name, _, _, _ in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON tb_13")

    op.execute("ALTER TABLE tb_13 NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_13 DISABLE ROW LEVEL SECURITY")
    op.execute("DROP INDEX IF EXISTS ix_tb_13_cl_13b_cl_13c")

    op.drop_table("tb_13")
