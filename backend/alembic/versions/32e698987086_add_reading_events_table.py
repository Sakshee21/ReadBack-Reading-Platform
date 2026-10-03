"""add reading_events table

Revision ID: 32e698987086
Revises: 5d9814daae2c
Create Date: 2026-10-03 19:46:34.368617

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32e698987086'
down_revision: Union[str, None] = '5d9814daae2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reading_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('book_id', sa.Integer(), nullable=True),
        sa.Column('chapter_id', sa.Integer(), nullable=True),
        sa.Column('micro_session_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('event_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['book_id'], ['books.id'], ),
        sa.ForeignKeyConstraint(['chapter_id'], ['chapters.id'], ),
        sa.ForeignKeyConstraint(['micro_session_id'], ['micro_sessions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reading_events_user_id'), 'reading_events', ['user_id'], unique=False)
    op.create_index(op.f('ix_reading_events_event_type'), 'reading_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_reading_events_created_at'), 'reading_events', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reading_events_created_at'), table_name='reading_events')
    op.drop_index(op.f('ix_reading_events_event_type'), table_name='reading_events')
    op.drop_index(op.f('ix_reading_events_user_id'), table_name='reading_events')
    op.drop_table('reading_events')
