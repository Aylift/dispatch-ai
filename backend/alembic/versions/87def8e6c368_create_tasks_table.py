"""create tasks table

Revision ID: 87def8e6c368
Revises: 
Create Date: 2026-08-16 16:24:19.010368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87def8e6c368'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tasks" not in inspector.get_table_names():
        op.create_table(
            "tasks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("text", sa.String(), nullable=False),
            sa.Column("done", sa.Boolean(), nullable=False),
            sa.Column("priority", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
    # Add with a server default so existing rows get a valid empty list.
    op.add_column('tasks', sa.Column('tags', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tasks', 'tags')
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "tasks" in inspector.get_table_names():
        op.drop_table("tasks")
