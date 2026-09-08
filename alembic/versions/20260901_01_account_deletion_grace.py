"""account deletion grace window: deleted_at column + purgeable foreign keys

Revision ID: 20260901_01
Revises: 20260831_02
Create Date: 2026-09-01

Deleting an account was a status flip and nothing else. The row, and everything
hanging off it, stayed forever — while the UI promised "Delete forever". This
migration is what makes the promise executable:

1. `tb_0.cl_0f` (deleted_at) records *when* the user asked, so the purge job has
   a deadline to compare against. `updated_at` cannot serve: it carries
   onupdate, so any later write would silently postpone the purge.

2. Every foreign key into `tb_0` gets an ON DELETE action, so destroying the
   user row destroys the rest with it. Without this, `DELETE FROM tb_0` fails on
   the first reference and the purge cannot run at all.

   - user-owned rows (streaks, friendships, chats, messages, user_badges,
     refresh tokens, device tokens) → CASCADE. They exist only because the user
     does.
   - `tb_7` audit logs → SET NULL on `cl_7c`. The log of the deletion has to
     outlive the account it describes, and `cl_7c` is nullable for exactly this.
     It is also the only workable option: `tb_7` has no UPDATE or DELETE policy
     under RLS, so nothing could clear the column from application code. A
     referential action runs as the table owner and is not subject to RLS.
   - `tb_4.cl_4b` (message → chat) → CASCADE, so a chat removed by the cascade
     above takes its messages with it rather than orphaning them.

Consequence worth stating plainly: purging an account also removes the *other*
participant's copy of the conversation. Both halves of a 1-on-1 chat live in one
`tb_3` row, and keeping it would leave a chat pointing at a user id that no
longer resolves.

The downgrade restores the FKs without an ON DELETE action and drops the column.
Rows already purged do not come back.
"""

from alembic import op
import sqlalchemy as sa

from core.config import config as appConfig


revision = "20260901_01"
down_revision = "20260831_02"
branch_labels = None
depends_on = None


# (table, column, referenced table, referenced column, ondelete)
_FOREIGN_KEYS = [
    ("tb_1", "cl_1b", "tb_0", "cl_0a", "CASCADE"),   # streak owner
    ("tb_2", "cl_2b", "tb_0", "cl_0a", "CASCADE"),   # friendship sender
    ("tb_2", "cl_2c", "tb_0", "cl_0a", "CASCADE"),   # friendship receiver
    ("tb_3", "cl_3b", "tb_0", "cl_0a", "CASCADE"),   # chat sender
    ("tb_3", "cl_3c", "tb_0", "cl_0a", "CASCADE"),   # chat receiver
    ("tb_4", "cl_4b", "tb_3", "cl_3a", "CASCADE"),   # message → chat
    ("tb_4", "cl_4c", "tb_0", "cl_0a", "CASCADE"),   # message sender
    ("tb_6", "cl_6b", "tb_0", "cl_0a", "CASCADE"),   # user_badge owner
    ("tb_7", "cl_7c", "tb_0", "cl_0a", "SET NULL"),  # audit log catalyst
    ("tb_8", "cl_8b", "tb_0", "cl_0a", "CASCADE"),   # refresh token owner
    ("tb_9", "cl_9b", "tb_0", "cl_0a", "CASCADE"),   # device token owner
]


def _constraintName(connection, table: str, column: str) -> str | None:
    """Find the FK constraint on (table, column), whatever Postgres named it.

    The baseline created these without explicit names, so they carry the
    server-generated `<table>_<column>_fkey`. Looking the name up instead of
    assuming it keeps this migration working on a database where one was
    recreated by hand under a different name.
    """
    return connection.execute(
        sa.text(
            """
            SELECT con.conname
              FROM pg_constraint con
              JOIN pg_class rel ON rel.oid = con.conrelid
              JOIN pg_attribute att
                ON att.attrelid = con.conrelid AND att.attnum = ANY(con.conkey)
             WHERE con.contype = 'f'
               AND rel.relname = :table
               AND att.attname = :column
             LIMIT 1
            """
        ),
        {"table": table, "column": column},
    ).scalar()


def _rebuildForeignKeys(ondelete: str | None) -> None:
    connection = op.get_bind()
    for table, column, refTable, refColumn, action in _FOREIGN_KEYS:
        name = _constraintName(connection, table, column)
        if name:
            op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            f"{table}_{column}_fkey",
            table,
            refTable,
            [column],
            [refColumn],
            ondelete=action if ondelete else None,
        )


def upgrade() -> None:
    op.add_column("tb_0", sa.Column("cl_0f", sa.DateTime(), nullable=True))

    # Accounts soft-deleted before this migration have no timestamp, so the
    # purge job would either skip them forever or destroy them on its first run
    # depending on how NULL is read. Stamping them now starts the grace window
    # from the deploy — the conservative reading, and the only one that gives
    # those users the window the new policy promises them.
    op.execute(
        sa.text(
            """
            UPDATE tb_0
               SET cl_0f = NOW() AT TIME ZONE 'UTC'
             WHERE cl_0e = :deleted
               AND cl_0f IS NULL
            """
        ).bindparams(deleted=appConfig.STATUS_CODES["deleted"])
    )

    _rebuildForeignKeys(ondelete=True)


def downgrade() -> None:
    _rebuildForeignKeys(ondelete=None)
    op.drop_column("tb_0", "cl_0f")
