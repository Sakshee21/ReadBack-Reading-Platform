"""add book theme

Revision ID: ff12d1075a25
Revises: 36777966249d
Create Date: 2026-10-05 00:49:19.341624

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff12d1075a25'
down_revision: Union[str, None] = '36777966249d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'books',
        sa.Column('theme', sa.String(length=32), nullable=False, server_default='parchment'),
    )


def downgrade() -> None:
    op.drop_column('books', 'theme')
