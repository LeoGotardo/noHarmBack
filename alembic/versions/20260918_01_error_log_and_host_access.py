"""error log and host access: tb_14, tb_15

Revision ID: 20260918_01
Revises: 20260916_03
Create Date: 2026-09-18

Two things the system did and then forgot.

## tb_14 — errors

`main.py` already catches every exception in three handlers and calls
`logger.exception`. That goes to stdout, into the Docker json-file driver, and
out again at the 10 MB rotation — so the answer to "has this been failing all
week?" has always been "the log that would have said so is gone".

**Grouped by fingerprint, not one row per occurrence.** A crash loop writes the
same failure thousands of times, and a table with thousands of identical rows
answers a question nobody asked. `cl_14e` is a hash of the exception type and
the top of the traceback; a repeat bumps `cl_14i` and moves `cl_14h`, and the
row count stays the number of *distinct* faults.

**The message and the traceback are encrypted; everything else is not.** That
split is the whole point of the table. A SQLAlchemy exception carries the
statement's parameters, so a failure inside `messageService` puts a message body
in the traceback and one inside `userService` puts an e-mail there — the exact
values `tb_4` and `tb_0` encrypt. Storing them in plaintext here would undo both.
The type, the path, the status and the fingerprint stay readable because they are
what grouping and filtering run on, and they carry no one's words.

`cl_14c` (the path) is plaintext even though a path contains a uid. `tb_7`
already stores uids in plaintext inside its descriptions; a different rule here
would be inconsistent without being more private.

## tb_15 — host access

Who logged into the box over SSH. Written by a script on the host, not by the
app: `auth.log` is outside the container, and mounting a root-owned file that
records every login on the machine into the application process is a wider grant
than this needs.

The natural key (`cl_15b`, `cl_15c`, `cl_15d`) is unique so the script can
re-send a window without creating duplicates — a cursor file that gets lost is
then a re-send, not a mess.

**What this is not**: proof. Anyone with root can edit `auth.log` before the
script reads it. It catches unexpected access and carelessness, not an attacker
covering their tracks.

## RLS

Both tables are readable only by a session with **no** `app.current_user_id` —
the same shape as `tb_11`. There is no version of "your own errors" that a user
should see, and an audit row about the host is not about any account at all.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "20260918_01"
down_revision = "20260916_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tb_14",
        sa.Column("cl_14a", UUID(as_uuid=True), primary_key=True),
        # kind: unhandled · domain · http
        sa.Column("cl_14b", sa.String(16), nullable=False),
        sa.Column("cl_14c", sa.String(512), nullable=False),   # path
        sa.Column("cl_14d", sa.String(8), nullable=False),     # method
        sa.Column("cl_14e", sa.String(64), nullable=False),    # fingerprint
        sa.Column("cl_14f", sa.String(128), nullable=False),   # exception type
        sa.Column("cl_14g", sa.Integer(), nullable=False),     # status code
        sa.Column("cl_14h", sa.DateTime(), nullable=False),    # last seen
        sa.Column("cl_14i", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cl_14j", sa.Text(), nullable=True),         # message, encrypted
        sa.Column("cl_14k", sa.Text(), nullable=True),         # traceback, encrypted
        # The account whose request it was, when there was one. SET NULL like
        # tb_7: an error outlives the account that happened to trigger it.
        sa.Column(
            "cl_14l",
            sa.String(),
            sa.ForeignKey("tb_0.cl_0a", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # One row per distinct fault: the write is an upsert on this.
    op.create_index("ix_tb_14_cl_14e", "tb_14", ["cl_14e"], unique=True)
    # "What broke recently", which is the only ordering the panel uses.
    op.create_index("ix_tb_14_cl_14h", "tb_14", ["cl_14h"])

    op.create_table(
        "tb_15",
        sa.Column("cl_15a", UUID(as_uuid=True), primary_key=True),
        sa.Column("cl_15b", sa.DateTime(), nullable=False),    # when
        sa.Column("cl_15c", sa.String(64), nullable=False),    # os user
        sa.Column("cl_15d", sa.String(64), nullable=False),    # source ip
        sa.Column("cl_15e", sa.String(32), nullable=False),    # method
        sa.Column("cl_15f", sa.String(16), nullable=False),    # accepted · failed
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    # The natural key, so a re-sent window is idempotent.
    op.create_index(
        "ix_tb_15_natural", "tb_15", ["cl_15b", "cl_15d", "cl_15c"], unique=True
    )

    for table in ("tb_14", "tb_15"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # No context means moderation, a job, or the app's own writer. A session
        # carrying a user is never one of those.
        op.execute(f"""
            CREATE POLICY {table}_admin_all ON {table}
            FOR ALL
            USING (current_setting('app.current_user_id', true) IS NULL
                   OR current_setting('app.current_user_id', true) = '')
            WITH CHECK (current_setting('app.current_user_id', true) IS NULL
                        OR current_setting('app.current_user_id', true) = '')
        """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tb_15_admin_all ON tb_15")
    op.execute("DROP POLICY IF EXISTS tb_14_admin_all ON tb_14")
    op.drop_index("ix_tb_15_natural", table_name="tb_15")
    op.drop_table("tb_15")
    op.drop_index("ix_tb_14_cl_14h", table_name="tb_14")
    op.drop_index("ix_tb_14_cl_14e", table_name="tb_14")
    op.drop_table("tb_14")
