"""admin board: the one index the measurements justified

Revision ID: 20260918_02
Revises: 20260918_01
Create Date: 2026-09-18

The admin board runs about seven aggregate queries per load. Four candidate
indexes were written for them and then measured against 50 000 accounts,
150 000 consent rows and 40 000 reports on a copy of the real schema. Three of
the four changed nothing, and are deliberately not here:

- **`tb_0 (cl_0e)`** for the status `GROUP BY` — not used at all, and obviously
  so in hindsight: a count over every row reads every row. 139 ms with and
  without.
- **`tb_13 (cl_13b, cl_13c, cl_13e DESC, cl_13a DESC)`** for the re-acceptance
  count — it removes the incremental sort, and the query takes the same 240 ms
  either way. The cost is materialising the newest row per (user, document)
  across the whole table, which the existing `(cl_13b, cl_13c)` index already
  serves; the ordering was never the expensive part. If 240 ms ever stops being
  acceptable behind the board's 60-second cache, the fix is one cross-joined
  query instead of one per document — not an index.
- **`tb_10 (cl_10j) WHERE cl_10i IS NOT NULL`** for stale review locks — the
  planner prefers a sequential scan at this size and was right to: 4.3 ms
  against 4.9 ms.

An index that is never chosen is not free. It is written on every insert and
update to the table, and this runs on a 913 MB instance where Postgres already
shares memory with Redis and the app.

## The one that stays

`ix_tb_0_cl_0f_deleted` turns the overdue-purge count from a sequential scan
into an index-only scan: **8.3 ms → 2.4 ms**, and it is the query whose answer
matters most — a non-zero result means `purge-accounts` has stopped running,
which `docs/TODO.md` describes as invisible from outside. Partial on
`cl_0e = 2` because soft-deleted rows are a small fraction of the table and the
question is never asked about any other status.
"""

from alembic import op


revision = "20260918_02"
down_revision = "20260918_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tb_0_cl_0f_deleted ON tb_0 (cl_0f) WHERE cl_0e = 2"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tb_0_cl_0f_deleted")
