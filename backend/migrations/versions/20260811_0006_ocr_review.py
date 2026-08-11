"""add OCR review pages, elements, and revisions"""
from alembic import op
import sqlalchemy as sa

revision = "20260811_0006"
down_revision = "20260811_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("documents", sa.Column("extraction_strategy", sa.String(30), nullable=False, server_default="AUTO"))
    op.create_table(
        "document_pages",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("document_id", sa.BigInteger(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("page_kind", sa.String(20), nullable=False, server_default="PAGE"),
        sa.Column("image_path", sa.String(1000), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),
    )
    op.create_index("ix_document_pages_document_id", "document_pages", ["document_id"])
    op.create_table(
        "ocr_elements",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("page_id", sa.BigInteger(), sa.ForeignKey("document_pages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False), sa.Column("y", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False), sa.Column("height", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float()),
        sa.Column("source", sa.String(20), nullable=False, server_default="OCR"),
        sa.Column("element_type", sa.String(20), nullable=False, server_default="TEXT_LINE"),
        sa.Column("reading_order", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("x >= 0 AND x <= 1 AND y >= 0 AND y <= 1", name="ck_ocr_element_origin"),
        sa.CheckConstraint("width >= 0 AND width <= 1 AND height >= 0 AND height <= 1", name="ck_ocr_element_size"),
        sa.CheckConstraint("version >= 1", name="ck_ocr_element_version"),
    )
    op.create_index("ix_ocr_elements_page_id", "ocr_elements", ["page_id"])
    op.create_table(
        "ocr_element_revisions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("element_id", sa.BigInteger(), sa.ForeignKey("ocr_elements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("changed_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("before_text", sa.Text(), nullable=False), sa.Column("after_text", sa.Text(), nullable=False),
        sa.Column("from_version", sa.Integer(), nullable=False), sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ocr_element_revisions_element_id", "ocr_element_revisions", ["element_id"])


def downgrade():
    op.drop_table("ocr_element_revisions")
    op.drop_table("ocr_elements")
    op.drop_table("document_pages")
    op.drop_column("documents", "extraction_strategy")
