"""add document_chunks table for RAG vector search

청크 한 조각 = 행 하나 = 벡터 하나. pgvector 의 HNSW 인덱스가 "테이블의 한 컬럼"을
색인하기 때문에 extracted_texts 에 배열로 넣는 방식은 색인이 불가능하다.

content_start / content_end 는 extracted_texts.content 안의 위치이며 리비전 0010 이
ocr_elements 에 넣은 것과 같은 좌표계다. 두 구간의 교집합으로 청크를 만든 element 를
찾고, element 의 x·y·width·height 로 원본 페이지에 검색 근거를 표시한다.
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "20260814_0011"
down_revision = "20260812_0010"
branch_labels = None
depends_on = None


EMBEDDING_DIM = 1024


def upgrade():
    # pgvector 확장. DB 이미지가 pgvector/pgvector:pg16 이어야 이 줄이 통과한다.
    # postgres:16-alpine 에서는 "extension \"vector\" is not available" 로 실패한다.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "document_id",
            sa.BigInteger(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("content_start", sa.Integer()),
        sa.Column("content_end", sa.Integer()),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("embedding_dim", sa.SmallInteger(), nullable=False),
        sa.Column("text_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("document_id", "seq", name="uq_document_chunk_seq"),
        sa.CheckConstraint("seq >= 0", name="ck_document_chunk_seq"),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number >= 1",
            name="ck_document_chunk_page_number",
        ),
        sa.CheckConstraint("char_count >= 0", name="ck_document_chunk_char_count"),
        sa.CheckConstraint("token_count >= 0", name="ck_document_chunk_token_count"),
        sa.CheckConstraint("text_version >= 1", name="ck_document_chunk_text_version"),
        sa.CheckConstraint(
            f"embedding_dim = {EMBEDDING_DIM}", name="ck_document_chunk_embedding_dim"
        ),
        sa.CheckConstraint(
            "content_start IS NULL OR content_start >= 0",
            name="ck_document_chunk_content_start",
        ),
        sa.CheckConstraint(
            "content_end IS NULL OR content_end >= content_start",
            name="ck_document_chunk_content_end",
        ),
    )

    # (document_id, seq) 조회는 uq_document_chunk_seq 가 만드는 btree 인덱스가
    # 그대로 처리하므로 같은 컬럼의 인덱스를 따로 만들지 않는다.
    op.create_index("ix_chunk_stale", "document_chunks", ["document_id", "text_version"])
    op.create_index("ix_chunk_model", "document_chunks", ["embedding_model", "document_id"])
    op.create_index(
        "ix_chunk_vec",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade():
    op.drop_index("ix_chunk_vec", table_name="document_chunks")
    op.drop_index("ix_chunk_model", table_name="document_chunks")
    op.drop_index("ix_chunk_stale", table_name="document_chunks")
    op.drop_table("document_chunks")
    # vector 확장은 지우지 않는다. 다른 객체가 이 확장의 타입을 참조하고 있으면
    # DROP EXTENSION 이 실패해서 downgrade 자체가 막힌다.
