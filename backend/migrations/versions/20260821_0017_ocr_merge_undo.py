"""OCR 박스 병합 이력 및 되돌리기

Revision ID: 20260821_0017
Revises: 20260820_0016
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "20260821_0017"
down_revision = "20260820_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ocr_merge_operations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("survivor_id", sa.BigInteger(), sa.ForeignKey("ocr_elements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("snapshot_json", postgresql.JSONB(), nullable=False),
        sa.Column("merged_version", sa.Integer(), nullable=False),
        sa.Column("undone_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ocr_merge_operations_document_id", "ocr_merge_operations", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_ocr_merge_operations_document_id", table_name="ocr_merge_operations")
    op.drop_table("ocr_merge_operations")
