"""add chapter section_kind

Revision ID: 8aea4010dd6d
Revises: b3ab23612b55
Create Date: 2026-10-13 21:21:52.628274

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8aea4010dd6d'
down_revision: Union[str, None] = 'b3ab23612b55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Label chapters story / front_matter / back_matter.

    Everything already in the database keeps 'story', so the five seeded books
    read exactly as before.
    """
    op.add_column(
        'chapters',
        sa.Column('section_kind', sa.String(length=16), nullable=False, server_default='story'),
    )


def downgrade() -> None:
    op.drop_column('chapters', 'section_kind')
