"""Add research documents: citation columns on books, research tags, key points

Research documents (papers and textbooks) are a separate track from the
reading-habit pilot. They reuse books/chapters/micro_sessions - a section is a
chapter, a chunk is a micro-session - so highlights, notes and citations work
unchanged. What they need of their own is citation metadata and their own tag
tables, kept apart from the literary themes so a research document can never
turn up in the pilot theme export.

Revision ID: c4a71f2b9d30
Revises: 68240945bbb6
"""

import sqlalchemy as sa
from alembic import op

revision = "c4a71f2b9d30"
down_revision = "68240945bbb6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Citation metadata. All nullable: a blank field means the document did not
    # say, which is deliberately different from a guess.
    op.add_column("books", sa.Column("doc_kind", sa.String(length=16), nullable=True))
    op.add_column("books", sa.Column("venue", sa.String(length=300), nullable=True))
    op.add_column("books", sa.Column("doi", sa.String(length=200), nullable=True))
    op.add_column("books", sa.Column("page_count", sa.Integer(), nullable=True))
    # What the extractor could not do with this document, and the figure and
    # table captions it held back, so both can be shown without re-parsing.
    op.add_column("books", sa.Column("research_notes", sa.JSON(), nullable=True))

    op.create_table(
        "research_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("micro_session_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=8), server_default="llm", nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tag_list_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["micro_session_id"], ["micro_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "micro_session_id", "tag", "source", name="uq_research_tags_chunk_tag_source"
        ),
    )
    op.create_index(
        "ix_research_tags_micro_session_id", "research_tags", ["micro_session_id"]
    )

    op.create_table(
        "research_tagging",
        sa.Column("micro_session_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("tag_list_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["micro_session_id"], ["micro_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("micro_session_id"),
    )

    op.create_table(
        "section_key_points",
        sa.Column("chapter_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("prompt_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("claimed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("error", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chapter_id"),
    )


def downgrade() -> None:
    op.drop_table("section_key_points")
    op.drop_table("research_tagging")
    op.drop_index("ix_research_tags_micro_session_id", table_name="research_tags")
    op.drop_table("research_tags")
    op.drop_column("books", "research_notes")
    op.drop_column("books", "page_count")
    op.drop_column("books", "doi")
    op.drop_column("books", "venue")
    op.drop_column("books", "doc_kind")
