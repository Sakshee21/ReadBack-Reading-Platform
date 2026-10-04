"""add visualization artwork to micro_sessions

Revision ID: 36777966249d
Revises: 3eea510acce6
Create Date: 2026-10-04 23:01:48.614694

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36777966249d'
down_revision: Union[str, None] = '3eea510acce6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('micro_sessions', sa.Column('visualization_image', sa.String(length=255), nullable=True))
    op.add_column('micro_sessions', sa.Column('visualization_alt', sa.Text(), nullable=True))
    op.add_column('micro_sessions', sa.Column('visualization_attribution', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('micro_sessions', 'visualization_attribution')
    op.drop_column('micro_sessions', 'visualization_alt')
    op.drop_column('micro_sessions', 'visualization_image')
