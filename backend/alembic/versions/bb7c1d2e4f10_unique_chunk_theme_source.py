"""one tag per theme, chunk and source

Revision ID: bb7c1d2e4f10
Revises: aa031ee3ec6c
Create Date: 2026-10-18 23:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'bb7c1d2e4f10'
down_revision: Union[str, None] = 'aa031ee3ec6c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # keep the newest row if two runs ever stored the same tag twice
    op.execute(
        "DELETE FROM micro_session_themes a USING micro_session_themes b "
        "WHERE a.micro_session_id = b.micro_session_id AND a.theme = b.theme "
        "AND a.source = b.source AND a.id < b.id"
    )
    op.create_unique_constraint(
        'uq_msthemes_chunk_theme_source', 'micro_session_themes', ['micro_session_id', 'theme', 'source']
    )


def downgrade() -> None:
    op.drop_constraint('uq_msthemes_chunk_theme_source', 'micro_session_themes', type_='unique')
