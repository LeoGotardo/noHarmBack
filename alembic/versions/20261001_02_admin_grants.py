"""admin grants: tb_19

Revision ID: 20261001_02
Revises: 20261001_01
Create Date: 2026-10-01

Until now an administrator was a uid in `ADMIN_USER_IDS`, and the only way to
add one was to edit the environment and redeploy. `tb_19` is the second source:
one row per account an official account promoted from inside the app.

The allowlist stays. It is how the first administrator exists before anyone can
promote anyone, and an entry there cannot be revoked from the app — what the
environment grants, only the environment takes back.

## RLS

Who is an administrator is already public (the "Admin" mark beside a name), so
SELECT is open. Writes pass only without a context — the admin routes' `getDb`
— so no account can promote itself through a session scoped to it. The
authorisation that matters (official accounts only) is the route's.
"""

from alembic import op
import sqlalchemy as sa


revision = "20261001_02"
down_revision = "20261001_01"
branch_labels = None
depends_on = None


_POLICIES = [
    ("tb_19_select_all", "SELECT", "true", None),
    ("tb_19_insert_admin", "INSERT", None, "app_current_user_id() IS NULL"),
    ("tb_19_delete_admin", "DELETE", "app_current_user_id() IS NULL", None),
]


def upgrade() -> None:
    op.create_table(
        "tb_19",
        sa.Column("cl_19a", sa.String(), nullable=False),
        sa.Column("cl_19b", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cl_19a"], ["tb_0.cl_0a"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cl_19a"),
    )

    op.execute("ALTER TABLE tb_19 ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_19 FORCE ROW LEVEL SECURITY")

    for name, command, using, check in _POLICIES:
        sql = f"CREATE POLICY {name} ON tb_19 FOR {command} TO PUBLIC"
        if using is not None:
            sql += f" USING ({using})"
        if check is not None:
            sql += f" WITH CHECK ({check})"
        op.execute(sql)


def downgrade() -> None:
    for name, _, _, _ in _POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON tb_19")

    op.execute("ALTER TABLE tb_19 NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tb_19 DISABLE ROW LEVEL SECURITY")

    op.drop_table("tb_19")
