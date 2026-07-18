"""chunk traceability and vector index

Revision ID: 002
Revises: 001
Create Date: 2026-07-18
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("chunk_uid", sa.String(length=64), nullable=True))
    op.add_column("document_chunks", sa.Column("chunk_source", sa.String(length=100), nullable=True))
    op.execute("UPDATE document_chunks SET chunk_source = 'brief_summary' WHERE chunk_source IS NULL")
    op.execute("UPDATE document_chunks SET chunk_uid = 'legacy-' || id::text WHERE chunk_uid IS NULL")
    op.alter_column("document_chunks", "chunk_uid", nullable=False)
    op.alter_column("document_chunks", "chunk_source", nullable=False)
    op.create_index("ix_document_chunks_chunk_uid", "document_chunks", ["chunk_uid"], unique=True)
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.drop_index("ix_document_chunks_chunk_uid", table_name="document_chunks")
    op.drop_column("document_chunks", "chunk_source")
    op.drop_column("document_chunks", "chunk_uid")
