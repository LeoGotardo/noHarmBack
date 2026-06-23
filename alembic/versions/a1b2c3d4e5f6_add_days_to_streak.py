"""add last_checkin to streak

Revision ID: a1b2c3d4e5f6
Revises: dd9051ae5321
Create Date: 2026-06-22

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e8a18a96f538'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # cl_1g stores the encrypted last_checkin timestamp (nullable)
    op.add_column('tb_1', sa.Column('cl_1g', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('tb_1', 'cl_1g')
