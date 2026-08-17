"""add task description column

Revision ID: a1b2c3d4e5f6
Revises: 87def8e6c368
Create Date: 2026-08-17 08:21:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '87def8e6c368'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("tasks")]
    if "description" not in columns:
        op.add_column('tasks', sa.Column('description', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tasks', 'description')
