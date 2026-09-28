"""name and picture sanctions: tb_0.cl_0h, tb_0.cl_0i

Revision ID: 20260916_01
Revises: 20260914_01
Create Date: 2026-09-16

Moderation could warn, suspend or ban. All three answer *conduct*, and none of
them answers the two reports this app actually gets about a profile: a username
impersonating someone, and a picture that does not belong in a recovery app.
A ban is far too much for either, and a warning changes nothing — the name and
the photo stay exactly where they are while the user decides whether to care.

Two flags, each the narrowest thing that ends the harm:

`cl_0h` — the account must choose a new username before it can be used again.
The offending name is **not** left in place waiting for them: the service
renames the account to a neutral generated handle in the same transaction, and
this flag is what makes the app insist on a real one. Renaming rather than
hiding is deliberate — a placeholder would have to be applied at every read
path (search, friend lists, chat headers, public profiles, push payloads), and
the one that gets missed is the one still showing the name. The original is not
lost: it is in the report's evidence (`tb_11`, captured at filing) and in the
audit log.

`cl_0i` — the account's picture is blocked. The column is not a copy of "has
no picture": `cl_0d` is nulled at the same time, and the flag is what stops it
coming straight back. `AuthService._syncProfilePicture` refreshes the photo
from the Google claim on every login, so without this the block would last
until the user next signed in. It also refuses an upload once one exists.

Both are reversible by an admin, and neither touches `cl_0e`: an account under
either sanction is a working account. That is the point of having them.

NOT NULL with a server default of false, so every existing row reads "no
sanction" without a backfill.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260916_01"
down_revision = "20260914_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tb_0",
        sa.Column("cl_0h", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tb_0",
        sa.Column("cl_0i", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # Partial indexes: both columns are false for almost every row, and the
    # only questions asked of them are "who is under a sanction".
    op.execute("CREATE INDEX IF NOT EXISTS ix_tb_0_cl_0h ON tb_0 (cl_0h) WHERE cl_0h")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tb_0_cl_0i ON tb_0 (cl_0i) WHERE cl_0i")


def downgrade() -> None:
    # Dropping these lifts every sanction, and the renamed accounts keep their
    # generated handles — the old names live in tb_11, not here, so there is
    # nothing to restore and nothing to lose.
    op.execute("DROP INDEX IF EXISTS ix_tb_0_cl_0h")
    op.execute("DROP INDEX IF EXISTS ix_tb_0_cl_0i")
    op.drop_column("tb_0", "cl_0i")
    op.drop_column("tb_0", "cl_0h")
