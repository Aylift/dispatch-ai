"""add task parent_id for subtasks

Revision ID: e5f6070819a0
Revises: d4e5f6070819
Create Date: 2026-08-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6070819a0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6070819'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("tasks")]
    if "parent_id" not in columns:
        op.add_column('tasks', sa.Column('parent_id', sa.Integer(), nullable=True))
        op.create_foreign_key(
            'fk_tasks_parent_id', 'tasks', 'tasks',
            ['parent_id'], ['id'], ondelete='CASCADE',
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_tasks_parent_id', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'parent_id')
