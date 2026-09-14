"""timed suspensions: tb_0.cl_0g

Revision ID: 20260911_02
Revises: 20260911_01
Create Date: 2026-09-11

Moderation could do two things to an account: nothing, or ban it for ever.
`cl_0e` is a single status, so "muted for 48 hours" and "suspended for a week"
had no way to be expressed — which meant every offence that did not deserve a
permanent ban got a warning nobody could enforce, and the ladder in the
moderation policy stopped at its second rung.

`cl_0g` is when a ban ends. The status is unchanged: a suspended account is
`banned` (9), exactly like a permanent one, so every refusal already written —
login, register, reactivate, refresh, and the status check on every
authenticated request — keeps working with no new branch. The column only
decides when that stops applying.

NULL is deliberately overloaded and reads the same either way: an account that
is not banned has no end date, and a permanent ban has no end date. Nothing
distinguishes them because nothing needs to.

## No cron

The ban lifts itself on the first sign-in after the date, in
`AuthService._liftExpiredSuspension`. A scheduled sweep was the obvious
alternative and is worse: it is a second thing that has to be installed and can
silently stop (the account purge is already one), and it would do work for
accounts nobody is trying to use. The cost of the lazy version is that
`tb_0.cl_0e` reads `banned` for an account whose suspension expired — true only
until someone tries to use it, and the moderation queue reads `cl_0g` beside
the status anyway.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260911_02"
down_revision = "20260911_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tb_0", sa.Column("cl_0g", sa.DateTime(), nullable=True))

    # Not encrypted, unlike most of tb_0: a moderator filters and sorts on it
    # ("whose suspension ends this week"), and it says nothing about the person
    # that `cl_0e = 9` in the same row does not already say.
    op.execute("CREATE INDEX IF NOT EXISTS ix_tb_0_cl_0g ON tb_0 (cl_0g)")


def downgrade() -> None:
    # Every suspension becomes permanent, which is the only honest direction:
    # the dates are the thing being removed, and an account mid-suspension must
    # not come back enabled because the column went away.
    op.execute("DROP INDEX IF EXISTS ix_tb_0_cl_0g")
    op.drop_column("tb_0", "cl_0g")
