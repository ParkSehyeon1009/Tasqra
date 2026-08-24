"""OCR 병합·분할 작업 이력

Revision ID: 20260821_0018
Revises: 20260821_0017
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "20260821_0018"
down_revision = "20260821_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ocr_structure_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_id", sa.BigInteger(), sa.ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("details_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_ocr_structure_events_document_id", "ocr_structure_events", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_ocr_structure_events_document_id", table_name="ocr_structure_events")
    op.drop_table("ocr_structure_events")
