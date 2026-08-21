"""add task timebox/status/elapsed/due_date columns

Revision ID: c3d4e5f60708
Revises: b2c3d4e5f607
Create Date: 2026-08-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f60708'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f607'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("tasks")]
    if "timebox_minutes" not in columns:
        op.add_column('tasks', sa.Column('timebox_minutes', sa.Integer(), nullable=True))
    if "status" not in columns:
        op.add_column('tasks', sa.Column('status', sa.String(), nullable=False, server_default='todo'))
    if "started_at" not in columns:
        op.add_column('tasks', sa.Column('started_at', sa.DateTime(), nullable=True))
    if "elapsed_seconds" not in columns:
        op.add_column('tasks', sa.Column('elapsed_seconds', sa.Integer(), nullable=False, server_default='0'))
    if "due_date" not in columns:
        op.add_column('tasks', sa.Column('due_date', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tasks', 'due_date')
    op.drop_column('tasks', 'elapsed_seconds')
    op.drop_column('tasks', 'started_at')
    op.drop_column('tasks', 'status')
    op.drop_column('tasks', 'timebox_minutes')
