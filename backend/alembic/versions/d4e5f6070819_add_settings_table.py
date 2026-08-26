"""add settings table

Revision ID: d4e5f6070819
Revises: c3d4e5f60708
Create Date: 2026-08-26 18:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6070819'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f60708'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("settings"):
        op.create_table(
            'settings',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('page_size', sa.Integer(), nullable=False, server_default='10'),
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('settings')
