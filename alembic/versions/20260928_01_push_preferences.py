"""device tokens: one row per device, and the preferences it was registered with

Revision ID: 20260928_01
Revises: 20260918_02
Create Date: 2026-09-28

Two faults in `tb_9`, fixed together because the second needs the first.

**Duplicate rows.** `POST /notifications` inserted unconditionally, and the app
registers its token on every start — so one phone held one row per launch, and
`sendPushToUser` delivered the same notification once per row. The upgrade keeps
the most recently touched row of each (owner, token) pair, deletes the rest, and
a unique index stops it recurring; registration is now an upsert.

**Preferences the server never saw.** The switches in Settings lived only in the
app's local storage, so they filtered what the app showed while open and did
nothing about a push sent while it was closed — which is the only push FCM ever
has to deliver. The Privacy Policy had to tell people to use their phone's
settings instead. Each row now carries the two categories the app offers:

- `cl_9e` — new messages
- `cl_9f` — friend activity (a request received, a request accepted)

Per device rather than per account, because that is how the app presents them:
the switches are read from the device they are shown on, and someone may want
messages on their phone and not on a tablet. The master switch is not a column:
turning it off unregisters the token, which also silences badge pushes.

TRUE by default so every existing row keeps doing what it did before.
"""

from alembic import op
import sqlalchemy as sa

revision = "20260928_01"
down_revision = "20260918_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Newest row per (owner, token) survives; ties broken by id so the delete
    # is deterministic when two rows were written in the same instant.
    op.execute(
        """
        DELETE FROM tb_9 a
        USING tb_9 b
        WHERE a.cl_9b = b.cl_9b
          AND a.cl_9c_h = b.cl_9c_h
          AND (a.updated_at, a.cl_9a) < (b.updated_at, b.cl_9a)
        """
    )
    op.create_index("ux_tb_9_owner_token", "tb_9", ["cl_9b", "cl_9c_h"], unique=True)

    op.add_column(
        "tb_9",
        sa.Column("cl_9e", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "tb_9",
        sa.Column("cl_9f", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    # The deleted duplicates are not restored: they were the same token, and
    # restoring them would only bring the duplicate pushes back.
    op.drop_column("tb_9", "cl_9f")
    op.drop_column("tb_9", "cl_9e")
    op.drop_index("ux_tb_9_owner_token", table_name="tb_9")
