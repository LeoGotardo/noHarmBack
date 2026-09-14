"""moderator locks on reports: tb_10.cl_10i / cl_10j

Revision ID: 20260911_03
Revises: 20260911_02
Create Date: 2026-09-11

A report had two states a moderator could see — open, or resolved — and no way
to say "I am reading this one". With more than one moderator that is a queue
where two people open the same report, read the same private conversation and
act on it twice: two suspensions for one offence, or one moderator dismissing
what the other just actioned.

`cl_10i` is who holds it and `cl_10j` is when they took it. "In review" is those
two columns plus a clock, not a new status code: `STATUS_CODES` is shared
configuration that the front end mirrors (`VITE_STATUS_CONSTANTS`), and adding a
value there to express a transient, moderator-only condition would make every
deployment agree on a constant no client ever sees.

## The lock expires, and that is the point

`REPORT_LOCK_MINUTES` (default 30) after `cl_10j` the lock is ignored and anyone
may claim it. A moderator who closes the tab, loses the tab, or goes home must
not park a report for ever — the failure mode of a lock with no expiry is a
queue that slowly fills with items nobody can touch, and the fix for that is
always a manual database edit.

Nothing is enforced by the database: the claim is a conditional UPDATE in
`ReportRepository.claim`, and `resolve` refuses a report held by someone else.
Both run in the admin routes' context-free session, which is the only thing
`tb_10`'s UPDATE policy lets through.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260911_03"
down_revision = "20260911_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tb_10", sa.Column("cl_10i", sa.String(), nullable=True))
    op.add_column("tb_10", sa.Column("cl_10j", sa.DateTime(), nullable=True))

    # No foreign key on cl_10i for the same reason as the evidence table: it
    # names a moderator, and the record of who reviewed a report has to survive
    # that person's account.


def downgrade() -> None:
    op.drop_column("tb_10", "cl_10j")
    op.drop_column("tb_10", "cl_10i")
