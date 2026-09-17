"""Add reviewed travel sources and a separate local-Chinese vector index."""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "d3f7a9021456"
down_revision = "c2e6f8a90123"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table("knowledge_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_key", sa.String(100), nullable=False, unique=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("poi_name", sa.String(100), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("reviewed_on", sa.String(10), nullable=False),
        sa.Column("expires_on", sa.String(10), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_knowledge_documents_city", "knowledge_documents", ["city"])
    op.create_table("knowledge_chunks",
        sa.Column("id", sa.String(140), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("knowledge_documents.id"), nullable=False),
        sa.Column("topic", sa.String(40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("embedding_vec", Vector(512), nullable=False),
    )
    op.create_index("ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"])


def downgrade():
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
