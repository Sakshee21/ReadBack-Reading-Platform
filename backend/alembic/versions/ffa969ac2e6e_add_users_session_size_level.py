"""add users.session_size_level

Revision ID: ffa969ac2e6e
Revises: 32e698987086
Create Date: 2026-10-03 19:56:50.416506

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ffa969ac2e6e'
down_revision: Union[str, None] = '32e698987086'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('session_size_level', sa.Integer(), nullable=False, server_default='1'),
    )


def downgrade() -> None:
    op.drop_column('users', 'session_size_level')
