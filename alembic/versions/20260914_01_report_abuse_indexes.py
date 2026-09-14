"""indexes for the per-reporter report ceilings

Revision ID: 20260914_01
Revises: 20260911_04
Create Date: 2026-09-14

Filing a report now asks `tb_10` three questions it was never asked before, and
every one of them runs on the request path of `POST /reports/{userId}`:

- has this reporter already reported this person, and how did it end
  (`cl_10b` + `cl_10g`)
- how many of this reporter's reports are still unreviewed
  (`cl_10b` + `cl_10f`)
- and, for the queue, how each reporter's past reports were decided
  (`cl_10b` + `cl_10f` again, grouped)

Single-column indexes on `cl_10b` (20260909_01) and `cl_10g` (20260911_01)
already exist, so none of this is a sequential scan today. The composites are
what keep it that way once one reporter has a long history: the pair lookup
stops reading every report that reporter ever filed, and the open-count and the
standings tally are answered from the index alone.

Indexes only — no column, no policy, nothing to backfill. The ceilings
themselves are `ReportService._assertPairAllowed` / `_assertBacklogUnderCap`
and the Redis quota in `ReportQuotaLimiter`, none of which the database knows
about.
"""

from alembic import op


revision = "20260914_01"
down_revision = "20260911_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The pair lookup: "this reporter's most recent report about this user".
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tb_10_cl_10b_cl_10g "
        "ON tb_10 (cl_10b, cl_10g)"
    )

    # The backlog cap and the reporter standings, both of which group a
    # reporter's rows by status.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tb_10_cl_10b_cl_10f "
        "ON tb_10 (cl_10b, cl_10f)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tb_10_cl_10b_cl_10f")
    op.execute("DROP INDEX IF EXISTS ix_tb_10_cl_10b_cl_10g")
