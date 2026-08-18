"""add task recurring columns

Revision ID: b2c3d4e5f607
Revises: a1b2c3d4e5f6
Create Date: 2026-08-18 08:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f607'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("tasks")]
    if "recurring" not in columns:
        op.add_column('tasks', sa.Column('recurring', sa.Boolean(), nullable=False, server_default=sa.false()))
    if "last_completed_date" not in columns:
        op.add_column('tasks', sa.Column('last_completed_date', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tasks', 'last_completed_date')
    op.drop_column('tasks', 'recurring')
