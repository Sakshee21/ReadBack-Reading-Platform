"""drop visualization artwork columns

Revision ID: a43e349b8ca4
Revises: ff12d1075a25
Create Date: 2026-10-06 22:05:13.432164

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a43e349b8ca4'
down_revision: Union[str, None] = 'ff12d1075a25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the curated-artwork columns.

    The "Picture this scene" checkpoint is now imagination-only: revealing a
    picture would supply the imagery the reader is meant to generate, which
    undercuts the dual-coding rationale the project rests on. The prompt and
    its has_visualization_prompt flag stay.
    """
    op.drop_column('micro_sessions', 'visualization_attribution')
    op.drop_column('micro_sessions', 'visualization_alt')
    op.drop_column('micro_sessions', 'visualization_image')


def downgrade() -> None:
    op.add_column('micro_sessions', sa.Column('visualization_image', sa.String(length=255), nullable=True))
    op.add_column('micro_sessions', sa.Column('visualization_alt', sa.Text(), nullable=True))
    op.add_column('micro_sessions', sa.Column('visualization_attribution', sa.Text(), nullable=True))
