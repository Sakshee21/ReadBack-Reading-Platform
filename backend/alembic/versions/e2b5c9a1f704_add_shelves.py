"""Add shelves: a reader's own groupings of books

Shelves hold references, not books. Putting a book on one changes nothing
about the book, and deleting a shelf leaves every book in the library - which
is why both sides cascade and nothing else does.

Revision ID: e2b5c9a1f704
Revises: c4a71f2b9d30
"""

import sqlalchemy as sa
from alembic import op

revision = "e2b5c9a1f704"
down_revision = "c4a71f2b9d30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shelves",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=40), nullable=False),
        # The folded name, so "Crime" and "crime" cannot both exist for one
        # reader whatever the database collation does.
        sa.Column("name_key", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "name_key", name="uq_shelf_user_name"),
    )
    op.create_index("ix_shelves_user_id", "shelves", ["user_id"])
    op.create_index("ix_shelves_user_position", "shelves", ["user_id", "position"])

    op.create_table(
        "shelf_books",
        sa.Column("shelf_id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["shelf_id"], ["shelves.id"], ondelete="CASCADE"),
        # Deleting an uploaded book takes it off every shelf it was on.
        sa.ForeignKeyConstraint(["book_id"], ["books.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("shelf_id", "book_id"),
    )
    op.create_index("ix_shelf_books_book_id", "shelf_books", ["book_id"])


def downgrade() -> None:
    op.drop_index("ix_shelf_books_book_id", table_name="shelf_books")
    op.drop_table("shelf_books")
    op.drop_index("ix_shelves_user_position", table_name="shelves")
    op.drop_index("ix_shelves_user_id", table_name="shelves")
    op.drop_table("shelves")
