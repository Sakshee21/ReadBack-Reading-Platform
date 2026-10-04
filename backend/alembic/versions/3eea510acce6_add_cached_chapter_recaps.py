"""add cached chapter recaps

Revision ID: 3eea510acce6
Revises: ffa969ac2e6e
Create Date: 2026-10-04 22:55:12.843128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3eea510acce6'
down_revision: Union[str, None] = 'ffa969ac2e6e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chapters', sa.Column('recap_text', sa.Text(), nullable=True))
    op.add_column('chapters', sa.Column('story_so_far', sa.Text(), nullable=True))
    op.add_column(
        'chapters',
        sa.Column('recap_source', sa.String(length=16), nullable=False, server_default='extractive'),
    )


def downgrade() -> None:
    op.drop_column('chapters', 'recap_source')
    op.drop_column('chapters', 'story_so_far')
    op.drop_column('chapters', 'recap_text')
