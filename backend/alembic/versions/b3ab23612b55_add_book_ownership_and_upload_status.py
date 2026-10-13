"""add book ownership and upload status

Revision ID: b3ab23612b55
Revises: a43e349b8ca4
Create Date: 2026-10-13 20:40:30.966673

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3ab23612b55'
down_revision: Union[str, None] = 'a43e349b8ca4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Uploads have no Gutenberg origin. Postgres allows many NULLs under a
    # unique index, so the existing uniqueness on real ids still holds.
    op.alter_column('books', 'gutenberg_id', existing_type=sa.Integer(), nullable=True)

    op.add_column('books', sa.Column('owner_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_books_owner_user', 'books', 'users', ['owner_user_id'], ['id'])
    op.create_index('ix_books_owner_user_id', 'books', ['owner_user_id'], unique=False)

    op.add_column(
        'books',
        sa.Column('is_user_uploaded', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'books',
        sa.Column('source_type', sa.String(length=16), nullable=False, server_default='seeded'),
    )
    op.add_column(
        'books',
        sa.Column('status', sa.String(length=16), nullable=False, server_default='ready'),
    )
    op.add_column('books', sa.Column('failure_reason', sa.Text(), nullable=True))

    # Everything already in the database is a shared seeded book.
    op.execute(
        "UPDATE books SET owner_user_id = NULL, is_user_uploaded = false, "
        "source_type = 'seeded', status = 'ready'"
    )


def downgrade() -> None:
    op.drop_column('books', 'failure_reason')
    op.drop_column('books', 'status')
    op.drop_column('books', 'source_type')
    op.drop_column('books', 'is_user_uploaded')
    op.drop_index('ix_books_owner_user_id', table_name='books')
    op.drop_constraint('fk_books_owner_user', 'books', type_='foreignkey')
    op.drop_column('books', 'owner_user_id')
    op.alter_column('books', 'gutenberg_id', existing_type=sa.Integer(), nullable=False)
