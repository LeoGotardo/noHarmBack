"""user reports: tb_10, its foreign keys and its row level security policies

Revision ID: 20260909_01
Revises: 20260902_01
Create Date: 2026-09-09

The app let a user block someone and nothing else. Blocking is a private
remedy — it hides two people from each other and tells nobody — so harassment,
impersonation and someone posting about a relapse in danger all ended at the
same dead end, with no record anyone could act on. This adds the record.

## Shape

`tb_10` is one row per report: who filed it (`cl_10b`), who it names
(`cl_10c`), a short reason code (`cl_10d`), the reporter's free text
(`cl_10e`) and a review status (`cl_10f`).

The reason stays plain text: moderation groups and filters on it, and a
six-value enum leaks nothing that the row's existence does not already say.
The details do not — that column is one user's prose about another user's
behaviour, the most sensitive thing in the schema after a message body, and it
is encrypted the same way.

`cl_10f` reuses STATUS_CODES rather than inventing a scale: `pending` (4) is an
unreviewed report, `accepted` (5) one a moderator acted on, `ignored` (6) one
they dismissed.

## The two foreign keys point opposite ways on purpose

`cl_10c` (the reported user) is ON DELETE CASCADE, like every other reference
into `tb_0`: once the purge job destroys an account there is nothing left to
moderate, and the reports about it go with it.

`cl_10b` (the reporter) is ON DELETE SET NULL, like `tb_7.cl_7c`. A report is
evidence about somebody *else*; letting a reporter erase it by deleting their
own account would make account deletion a way to unfile complaints. The column
is nullable for exactly this, and `Report.reporter` is Optional to match.

## RLS

The reporter may read and file their own reports. Nobody can read a report
filed about them — a reported user learning who reported them is the failure
mode that stops people reporting at all.

There is deliberately no UPDATE policy that any request-scoped session can
satisfy: `tb_10_update_admin` passes only when `app_current_user_id()` is NULL,
which is the context-free session the admin routes take through `getDb`. A
reporter cannot rewrite a filed report, and there is no DELETE policy at all,
so nobody removes one through the application.
"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


revision = "20260909_01"
down_revision = "20260902_01"
branch_labels = None
depends_on = None


_POLICIES = [
    # Read and file your own; the reported user is not a party to the row.
    ("tb_10_select_own", "SELECT",
     "app_current_user_id() IS NULL OR cl_10b = app_current_user_id()", None),
    ("tb_10_insert_own", "INSERT", None,
     "app_current_user_id() IS NULL OR cl_10b = app_current_user_id()"),
    # Only a session with no context — i.e. the admin routes' `getDb` — resolves
    # a report. No DELETE policy: rows are never removed from the application.
    ("tb_10_update_admin", "UPDATE",
     "app_current_user_id() IS NULL", "app_current_user_id() IS NULL"),
]


def upgrade() -> None:
    op.create_table(
        "tb_10",
        sa.Column("cl_10a", sa.UUID(), nullable=False),
        sa.Column("cl_10b", sa.String(), nullable=True),
        sa.Column("cl_10c", sa.String(), nullable=False),
        sa.Column("cl_10d", sa.String(length=32), nullable=False),
        sa.Column("cl_10e", sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(), nullable=True),
        sa.Column("cl_10f", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cl_10b"], ["tb_0.cl_0a"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["cl_10c"], ["tb_0.cl_0a"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cl_10a"),
    )

    # cl_10b carries the RLS predicate on every read; cl_10c is how moderation
    # asks "how many reports name this account". Both would be sequential scans
    # otherwise — see the note on POLICY_INDEXES in 20260831_02.
    op.execute("CREATE INDEX IF NOT EXISTS ix_tb_10_cl_10b ON tb_10 (cl_10b)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tb_10_cl_10c ON tb_10 (cl_10c)")

    op.execute("ALTER TABLE tb_10 ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_10 FORCE ROW LEVEL SECURITY")

    for name, command, using, check in _POLICIES:
        sql = f"CREATE POLICY {name} ON tb_10 FOR {command} TO PUBLIC"
        if using is not None:
            sql += f" USING ({using})"
        if check is not None:
            sql += f" WITH CHECK ({check})"
        op.execute(sql)


def downgrade() -> None:
    for name, _, _, _ in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON tb_10")

    op.execute("ALTER TABLE tb_10 NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_10 DISABLE ROW LEVEL SECURITY")

    op.execute("DROP INDEX IF EXISTS ix_tb_10_cl_10b")
    op.execute("DROP INDEX IF EXISTS ix_tb_10_cl_10c")

    op.drop_table("tb_10")
