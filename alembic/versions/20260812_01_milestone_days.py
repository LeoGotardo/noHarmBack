"""badge milestone becomes a day count instead of a timestamp

Revision ID: 20260812_01
Revises:
Create Date: 2026-08-12

`tb_5.cl_5d` (badge milestone) stored a calendar timestamp, but the domain rule
is "N clean days" — two users who started in different months need the same
milestone, not the same date. The column becomes INTEGER.

DESTRUCTIVE: the stored timestamps carry no day count, so existing values cannot
be converted and are reset to 0. Re-seed badge milestones after upgrading.
The downgrade restores the column type, not the original values.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260812_01"
# Chained after the baseline: before this, it was the only revision.
down_revision = "c0781a0a5605"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "tb_5",
        "cl_5d",
        existing_type=sa.DateTime(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using="0",
    )


def downgrade() -> None:
    op.alter_column(
        "tb_5",
        "cl_5d",
        existing_type=sa.Integer(),
        type_=sa.DateTime(),
        existing_nullable=False,
        postgresql_using="NULL::timestamp",
    )
