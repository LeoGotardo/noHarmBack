"""posts, comments and likes: tb_16, tb_17, tb_18 — plus what they need elsewhere

Revision ID: 20261001_01
Revises: 20260928_01
Create Date: 2026-10-01

The Community tab. Until now everything a user wrote went to one other person —
a friend, in a chat both of them had accepted. A post is the first thing in the
schema written for an audience, and most of this migration is the consequence
of that rather than the three tables themselves. `docs/POSTS_PLAN.md` is the
design; this is its schema.

## tb_16 — posts

Text only. `cl_16c` is encrypted like a message body (`tb_4.cl_4d`): a post in
a recovery app is very often about the recovery. `cl_16d` is the audience the
author chose — `friends` or `community` — and `cl_16e` the status: `enabled`
while it is up, `blocked` once a moderator removed it. The author deleting
their own post is a real DELETE, cascading to its comments and likes: whoever
deletes something expects it gone, and if it had been reported the copy is
already in `tb_11`.

`cl_16f` is when a moderator removed it. Removal is a status and not a delete
so an appeal can put it back; `purge-removed-content` deletes it once
`REMOVED_CONTENT_RETENTION_DAYS` have passed from this instant. A dedicated
column rather than `updated_at`, because the retention clock should start at
the removal and nothing else.

`created_at` stays in plaintext because the feed's cursor orders by it.

## tb_17 — comments

Same shape, one level down. Deleted by their author **or by the author of the
post** (D7): someone who wrote about their relapse should not have to wait for
a moderator to take a stranger's reply off it.

## tb_18 — likes

One row per (post, user), and the composite primary key is what makes a like
idempotent: `PUT /posts/{id}/like` twice is one like, because the second
INSERT is `ON CONFLICT DO NOTHING`. No `updated_at` — a like has no second
state. Likes never notify anyone (D6).

## Visibility is the service's, not RLS's

All three tables are readable by any session, like `tb_0`. Who can see a post
depends on friendships, blocks and the author's account status, and a policy
that tried to express that would be a second, slower copy of
`PostService.visibleTo` that nobody tests. What RLS does here is the part it is
good at: nobody writes as somebody else, and only a session with no context —
moderation, the purge job — can change a status.

## tb_2.cl_2g — who blocked whom

A block used to be a status on a friendship row and nothing more, so
`unblock` accepted either participant — including the one who was blocked.
Between friends that was unlikely to matter. With strangers able to comment on
each other, "unblock myself" is the first thing a harasser tries, so the row
now records who did it and only they may undo it. Rows blocked before this
column existed stay NULL and keep the old rule: there is no way to know.

The two composite indexes are for the visibility check, which asks "is there a
block between these two" for every author on a feed page.

## tb_9.cl_9g — the `community` push category

A comment on your post. TRUE by default like the other two, so a device that
registered before the switch existed keeps receiving it.

## tb_10.cl_10k — what a report was filed from

`chat`, `post`, `comment` or NULL. The report is still about a person; this
says where the moderator should look first.

## tb_12.cl_12h — the removed excerpt

A notice that says "a post of yours was removed" without saying which one is a
notice the recipient cannot act on. The first 200 characters are copied into
the notice, encrypted, because the post itself is purged after 30 days and the
notice is kept.
"""

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


revision = "20261001_01"
down_revision = "20260928_01"
branch_labels = None
depends_on = None


_CTX = "app_current_user_id()"

_POLICIES: dict[str, list[tuple[str, str, str | None, str | None]]] = {
    "tb_16": [
        # Visibility is PostService's job — see the module docstring.
        ("tb_16_select_any", "SELECT", "true", None),
        ("tb_16_insert_own", "INSERT", None, f"{_CTX} IS NULL OR cl_16b = {_CTX}"),
        # Only moderation changes a post: there is no edit (D3), and a status
        # the author could set would be a removal they could reverse.
        ("tb_16_update_admin", "UPDATE", f"{_CTX} IS NULL", f"{_CTX} IS NULL"),
        ("tb_16_delete_own", "DELETE", f"{_CTX} IS NULL OR cl_16b = {_CTX}", None),
    ],
    "tb_17": [
        ("tb_17_select_any", "SELECT", "true", None),
        ("tb_17_insert_own", "INSERT", None, f"{_CTX} IS NULL OR cl_17c = {_CTX}"),
        ("tb_17_update_admin", "UPDATE", f"{_CTX} IS NULL", f"{_CTX} IS NULL"),
        # The comment's author, or the author of the post it sits under (D7).
        ("tb_17_delete_own_or_post_author", "DELETE",
         f"{_CTX} IS NULL OR cl_17c = {_CTX} OR EXISTS ("
         f"  SELECT 1 FROM tb_16 WHERE tb_16.cl_16a = tb_17.cl_17b AND tb_16.cl_16b = {_CTX})",
         None),
    ],
    "tb_18": [
        # Open so a like count is a count; nothing here says who liked what to
        # anyone but the service, which never returns names.
        ("tb_18_select_any", "SELECT", "true", None),
        ("tb_18_insert_own", "INSERT", None, f"{_CTX} IS NULL OR cl_18b = {_CTX}"),
        ("tb_18_delete_own", "DELETE", f"{_CTX} IS NULL OR cl_18b = {_CTX}", None),
    ],
}

_INDEXES = [
    # The community feed: enabled posts, newest first, keyset on (created_at, id).
    ("ix_tb_16_feed", "tb_16", "(cl_16e, created_at DESC, cl_16a DESC)"),
    # The friends feed and a profile's posts: by author, newest first.
    ("ix_tb_16_author", "tb_16", "(cl_16b, created_at DESC)"),
    # A post's thread, oldest first.
    ("ix_tb_17_thread", "tb_17", "(cl_17b, created_at, cl_17a)"),
    ("ix_tb_17_cl_17c", "tb_17", "(cl_17c)"),
    ("ix_tb_18_cl_18b", "tb_18", "(cl_18b)"),
    # "Is there a block between these two" — asked in both directions.
    ("ix_tb_2_pair", "tb_2", "(cl_2b, cl_2c)"),
    ("ix_tb_2_pair_reverse", "tb_2", "(cl_2c, cl_2b)"),
]


def upgrade() -> None:
    op.create_table(
        "tb_16",
        sa.Column("cl_16a", sa.UUID(), nullable=False),
        sa.Column("cl_16b", sa.String(), nullable=False),
        sa.Column("cl_16c", sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(), nullable=False),
        sa.Column("cl_16d", sa.String(length=16), nullable=False),
        sa.Column("cl_16e", sa.Integer(), nullable=False),
        sa.Column("cl_16f", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cl_16b"], ["tb_0.cl_0a"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cl_16a"),
    )

    op.create_table(
        "tb_17",
        sa.Column("cl_17a", sa.UUID(), nullable=False),
        sa.Column("cl_17b", sa.UUID(), nullable=False),
        sa.Column("cl_17c", sa.String(), nullable=False),
        sa.Column("cl_17d", sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(), nullable=False),
        sa.Column("cl_17e", sa.Integer(), nullable=False),
        sa.Column("cl_17f", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cl_17b"], ["tb_16.cl_16a"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cl_17c"], ["tb_0.cl_0a"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cl_17a"),
    )

    op.create_table(
        "tb_18",
        sa.Column("cl_18a", sa.UUID(), nullable=False),
        sa.Column("cl_18b", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cl_18a"], ["tb_16.cl_16a"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cl_18b"], ["tb_0.cl_0a"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cl_18a", "cl_18b"),
    )

    op.add_column(
        "tb_2",
        sa.Column(
            "cl_2g",
            sa.String(),
            sa.ForeignKey("tb_0.cl_0a", name="fk_tb_2_cl_2g", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "tb_9",
        sa.Column("cl_9g", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column("tb_10", sa.Column("cl_10k", sa.String(length=16), nullable=True))
    op.add_column(
        "tb_12",
        sa.Column("cl_12h", sqlalchemy_utils.types.encrypted.encrypted_type.StringEncryptedType(), nullable=True),
    )

    for name, table, columns in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {columns}")

    for table, policies in _POLICIES.items():
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        for name, command, using, check in policies:
            sql = f"CREATE POLICY {name} ON {table} FOR {command} TO PUBLIC"
            if using is not None:
                sql += f" USING ({using})"
            if check is not None:
                sql += f" WITH CHECK ({check})"
            op.execute(sql)


def downgrade() -> None:
    for table, policies in _POLICIES.items():
        for name, _, _, _ in policies:
            op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")

    for name, _, _ in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")

    op.drop_column("tb_12", "cl_12h")
    op.drop_column("tb_10", "cl_10k")
    op.drop_column("tb_9", "cl_9g")
    op.drop_constraint("fk_tb_2_cl_2g", "tb_2", type_="foreignkey")
    op.drop_column("tb_2", "cl_2g")

    op.drop_table("tb_18")
    op.drop_table("tb_17")
    op.drop_table("tb_16")
